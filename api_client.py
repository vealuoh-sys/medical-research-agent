import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
import ssl

# Reconfigure stdout/stderr on Windows to handle UTF-8 symbols smoothly
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


# ==============================================================================
# SECTION 1: Unified SSL Request Handler
# ==============================================================================
def make_post_request(url, payload_bytes, headers=None):
    """
    Sends an HTTP POST request to the specified URL with JSON payload.
    Merges custom headers with default Content-Type and User-Agent headers.
    Handles SSL certificate fallbacks cleanly for corporate proxies.
    """
    req_headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (compatible; MedicalResearchAgent/1.0)'
    }
    if headers:
        req_headers.update(headers)
        
    req = urllib.request.Request(
        url,
        data=payload_bytes,
        headers=req_headers
    )
    
    try:
        context = ssl.create_default_context()
        return urllib.request.urlopen(req, context=context, timeout=120)
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" in str(e):
            context = ssl._create_unverified_context()
            return urllib.request.urlopen(req, context=context, timeout=120)
        raise e


# ==============================================================================
# SECTION 2: Groq API Credential Loader
# ==============================================================================
def get_groq_api_key():
    """
    Loads GROQ_API_KEY from environment variables or .env files.
    Priority order:
      1. os.environ["GROQ_API_KEY"]
      2. <project_dir>/.env
      3. ~/.env
    Prints the loaded file path and masked key at runtime.
    """
    env_var_key = os.environ.get("GROQ_API_KEY")
    if env_var_key:
        masked = env_var_key[:6] + "..." + env_var_key[-4:] if len(env_var_key) >= 10 else "***"
        print(f"  -> GROQ_API_KEY loaded from environment variable (Masked: {masked})")
        return env_var_key.strip()
        
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_paths = [
        os.path.join(script_dir, ".env"),
        os.path.expanduser("~/.env")
    ]
    for env_path in env_paths:
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GROQ_API_KEY="):
                            key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if key:
                                masked = key[:6] + "..." + key[-4:] if len(key) >= 10 else "***"
                                print(f"  -> GROQ_API_KEY loaded from file: {env_path} (Masked: {masked})")
                                return key
            except Exception:
                pass
                
    return None


# ==============================================================================
# SECTION 3: Gemini (Google AI Studio) Credential Loader — used as a fallback
# ==============================================================================
def get_gemini_api_key():
    """
    Loads GEMINI_API_KEY from environment variables or .env files, the same
    way get_groq_api_key() does. Optional — only used as a fallback when
    Groq fails or is rate-limited.
    """
    env_var_key = os.environ.get("GEMINI_API_KEY")
    if env_var_key:
        masked = env_var_key[:6] + "..." + env_var_key[-4:] if len(env_var_key) >= 10 else "***"
        print(f"  -> GEMINI_API_KEY loaded from environment variable (Masked: {masked})")
        return env_var_key.strip()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_paths = [
        os.path.join(script_dir, ".env"),
        os.path.expanduser("~/.env")
    ]
    for env_path in env_paths:
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GEMINI_API_KEY="):
                            key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if key:
                                masked = key[:6] + "..." + key[-4:] if len(key) >= 10 else "***"
                                print(f"  -> GEMINI_API_KEY loaded from file: {env_path} (Masked: {masked})")
                                return key
            except Exception:
                pass

    return None


# ==============================================================================
# SECTION 4: Raw Groq API Call (single provider, no fallback)
# ==============================================================================
def _call_groq_raw(prompt, api_key, model="llama-3.3-70b-versatile", temperature=0.0, seed=42):
    """
    Sends a structured prompt to Groq API (OpenAI-compatible endpoint).
    Executes automatic retry with exponential backoff on HTTP 429 rate limits.
    Fails loudly without silent default substitutions if retries are exhausted.
    Returns None on failure — never a placeholder/fabricated string.
    """
    masked = api_key[:6] + "..." + api_key[-4:] if api_key and len(api_key) >= 10 else "***"
    print(f"\n[Groq API Call] Model: {model} | Key: {masked} | Sending prompt...")

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": temperature,
        "seed": seed
    }
    payload_bytes = json.dumps(payload).encode("utf-8")

    for attempt in range(1, 5):
        try:
            with make_post_request(url, payload_bytes, headers=headers) as response:
                res_data = json.loads(response.read().decode("utf-8"))

            choices = res_data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content", "")
                if content:
                    return content

            print(f"Warning: Groq returned empty response content.")
            break

        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_header = e.headers.get("Retry-After") if e.headers else None
                if retry_header and retry_header.isdigit():
                    wait_sec = min(int(retry_header) + 2, 20)
                else:
                    wait_sec = 8 * attempt
                print(f"Rate limited (HTTP 429) on Groq API. Waiting {wait_sec}s (Attempt {attempt}/4)...")
                time.sleep(wait_sec)
                continue
            else:
                print(f"Groq API Error (HTTP {e.code}): {e.reason}")
                break
        except Exception as e:
            print(f"Error calling Groq API: {e}")
            break

    return None


# ==============================================================================
# SECTION 5: Raw Gemini API Call (fallback provider)
# ==============================================================================
def _call_gemini_raw(prompt, api_key, model="gemini-2.0-flash", temperature=0.0):
    """
    Sends a structured prompt to Google AI Studio's Gemini API.
    Returns None on failure — never a placeholder/fabricated string.
    """
    masked = api_key[:6] + "..." + api_key[-4:] if api_key and len(api_key) >= 10 else "***"
    print(f"\n[Gemini API Call] Model: {model} | Key: {masked} | Sending prompt...")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    headers = {}

    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": temperature
        }
    }
    payload_bytes = json.dumps(payload).encode("utf-8")

    for attempt in range(1, 4):
        try:
            with make_post_request(url, payload_bytes, headers=headers) as response:
                res_data = json.loads(response.read().decode("utf-8"))

            candidates = res_data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts)
                if text:
                    return text

            print("Warning: Gemini returned empty response content.")
            break

        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait_sec = 10 * attempt
                print(f"Rate limited (HTTP 429) on Gemini API. Waiting {wait_sec}s (Attempt {attempt}/3)...")
                time.sleep(wait_sec)
                continue
            else:
                print(f"Gemini API Error (HTTP {e.code}): {e.reason}")
                break
        except Exception as e:
            print(f"Error calling Gemini API: {e}")
            break

    return None


# ==============================================================================
# SECTION 6: Unified Call — tries Groq first, falls back to Gemini
# ==============================================================================
# Every pipeline stage calls this same function name (call_groq_api) unchanged,
# so the fallback is automatic and required no changes anywhere else in the
# pipeline. If GEMINI_API_KEY isn't set, this behaves exactly as before
# (Groq only). If both providers fail, it returns None honestly — it never
# invents a response to keep the pipeline moving.
def call_groq_api(prompt, api_key, model="llama-3.3-70b-versatile", temperature=0.0, seed=42):
    result = _call_groq_raw(prompt, api_key, model=model, temperature=temperature, seed=seed)
    if result:
        return result

    gemini_key = get_gemini_api_key()
    if not gemini_key:
        print("  -> No GEMINI_API_KEY configured, so no fallback is available.")
        return None

    print("  -> Groq failed. Falling back to Gemini...")
    return _call_gemini_raw(prompt, gemini_key, temperature=temperature)
