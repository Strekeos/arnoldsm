# .github/scripts/generate_images.py
import os
import re
import requests
import base64
import yaml
import time  # Import the time module
from pathlib import Path

# --- Configuration ---
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
API_URL = "https://api.together.xyz/inference"
# Consider changing this model temporarily for testing if FLUX continues to fail
MODEL = "black-forest-labs/FLUX.1-schnell-Free"

POSTS_DIR = Path("content/blogs")
IMAGES_DIR = Path("static/images/blogs") # Plural 'blogs'

# Delay between API calls in seconds
API_DELAY = 12

HEADERS = {
    "Authorization": f"Bearer {TOGETHER_API_KEY}",
    "Content-Type": "application/json"
}

PROMPT_TEMPLATE = "Create an abstract, aesthetically striking image representing: '{title}'"
# --- End Configuration ---

def generate_image(prompt: str) -> bytes:
    """Generates an image using the Together AI API."""
    if not TOGETHER_API_KEY:
        raise ValueError("TOGETHER_API_KEY environment variable not set.")

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "n": 1,
        "steps": 4, # Correct steps for FLUX
        "width": 512,
        "height": 512,
    }
    print(f"Sending request to Together API for prompt: '{prompt}'")
    response = requests.post(API_URL, headers=HEADERS, json=payload)

    try:
        response.raise_for_status() # Check for HTTP errors (4xx, 5xx)
    except requests.exceptions.RequestException as e:
        print(f"API Request failed: {e}")
        try:
            print(f"Response Status Code: {response.status_code}")
            print(f"Response Body: {response.text}")
        except Exception:
             print("Could not retrieve response details after initial error.")
        raise

    result = response.json()
    # print("Full API Response JSON:", result) # Uncomment for deep debugging

    # --- Start: Enhanced API Response Check ---
    image_data_base64 = None # Variable to hold the extracted data

    # Check primary expected structure: result['output']['choices'][0]['image_base64']
    if ("output" in result and
            "choices" in result["output"] and
            isinstance(result["output"]["choices"], list) and
            len(result["output"]["choices"]) > 0 and
            isinstance(result["output"]["choices"][0], dict) and
            "image_base64" in result["output"]["choices"][0]):

        image_data_base64 = result["output"]["choices"][0]["image_base64"]
        if not image_data_base64: # Check if the key exists but the value is empty/null
             print("Error: 'image_base64' key found in output.choices[0] but its value is empty.")
             print("API Response JSON:", result)
             raise RuntimeError("Image generation failed: API returned empty image data in choices.")

    # Fallback check for simpler structure: result['image_base64'] (Less common)
    elif "image_base64" in result:
         print("Warning: Using top-level 'image_base64'. Verify API response structure.")
         image_data_base64 = result["image_base64"]
         if not image_data_base64: # Check if the key exists but the value is empty/null
            print("Error: Top-level 'image_base64' key found but its value is empty.")
            print("API Response JSON:", result)
            raise RuntimeError("Image generation failed: API returned empty top-level image data.")

    # If image_data_base64 is still None after checks, raise error
    if image_data_base64 is None:
        # Provide more context if choices array was present but lacked data
        if ("output" in result and
            "choices" in result["output"] and
            isinstance(result["output"]["choices"], list) and
            len(result["output"]["choices"]) > 0):
            print("Error: 'choices' array exists but the first element is empty or missing 'image_base64'.")
        else:
             print("Error: Could not find 'image_base64' in any expected location in the API response.")

        print("API Response JSON:", result) # Print the problematic JSON
        raise RuntimeError("Image generation failed: API response did not contain valid image data.")
    # --- End: Enhanced API Response Check ---

    # If we got here, image_data_base64 should be valid
    try:
        return base64.b64decode(image_data_base64)
    except Exception as decode_error:
        print(f"Error decoding base64 data: {decode_error}")
        raise RuntimeError("Image generation failed: Could not decode base64 data from API.")


def parse_frontmatter(filepath: Path) -> dict:
    """Parses YAML frontmatter from a Markdown file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        # More robust regex allows for spaces around ---
        match = re.match(r"^\s*---\s*\n(.*?)\n\s*---\s*\n", content, re.DOTALL | re.MULTILINE)
        if match:
            frontmatter_str = match.group(1)
            front = yaml.safe_load(frontmatter_str)
            return front if isinstance(front, dict) else {}
        return {}
    except Exception as e: # Catch broader exceptions during file/parse
        print(f"Warning: Error reading or parsing {filepath}: {e}")
        return {}

def main():
    """Main function to find posts, generate missing images, and save them."""
    print(f"Starting image generation process.")
    print(f"Scanning posts in: {POSTS_DIR.resolve()}")
    print(f"Saving images to: {IMAGES_DIR.resolve()}")
    print(f"Using model: {MODEL}")
    print(f"API call delay set to: {API_DELAY} seconds")

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    generated_count = 0
    skipped_count = 0
    failed_count = 0
    processed_count = 0

    if not POSTS_DIR.is_dir():
        print(f"Error: Posts directory not found: {POSTS_DIR.resolve()}")
        return

    md_files = list(POSTS_DIR.glob("*.md"))
    total_files = len(md_files)
    print(f"Found {total_files} markdown files to process.")

    for md_file in md_files:
        processed_count += 1
        print(f"\nProcessing file {processed_count}/{total_files}: {md_file.name}")

        # Add delay *before* processing the next file (if not the first)
        if processed_count > 1:
             print(f"  - Waiting {API_DELAY} seconds before next API interaction...")
             time.sleep(API_DELAY)

        front = parse_frontmatter(md_file)
        if not front:
            print("  - No valid frontmatter found. Skipping.")
            skipped_count += 1
            continue

        image_path_str = front.get("featured_image", "")

        # Skip if missing, empty, or an external URL
        if not image_path_str or image_path_str.startswith(('http://', 'https://')):
            if not image_path_str:
                print(f"  - No 'featured_image' key in frontmatter. Skipping generation.")
            else:
                print(f"  - 'featured_image' path ('{image_path_str}') is a URL. Skipping generation.")
            skipped_count += 1
            continue

        image_filename = Path(image_path_str).name
        image_out_path = IMAGES_DIR / image_filename

        if image_out_path.exists():
            print(f"  - Image already exists: {image_out_path}. Skipping generation.")
            skipped_count += 1
            continue

        title = front.get("title")
        if not title:
            title = md_file.stem.replace("-", " ").replace("_", " ").capitalize()
            print(f"  - No 'title' in frontmatter, using generated title: '{title}'")

        prompt = PROMPT_TEMPLATE.format(title=title)
        print(f"  - Generating image for title: '{title}'")
        print(f"  - Output path: {image_out_path}")

        try:
            img_data = generate_image(prompt) # Call the updated function
            with open(image_out_path, "wb") as img_file:
                img_file.write(img_data)
            print(f"  - Successfully generated and saved image: {image_out_path}")
            generated_count += 1
        except Exception as e:
            # Error details should have been printed within generate_image() or parse_frontmatter()
            print(f"  - FAILED to generate image for {md_file.name}. Error: {e}")
            failed_count += 1
            # Optional: Decide if you want to stop on failure
            # raise

    print("\n--- Image Generation Summary ---")
    print(f"Generated: {generated_count}")
    print(f"Skipped (exists, no path, or URL): {skipped_count}")
    print(f"Failed: {failed_count}")
    print("------------------------------")

if __name__ == "__main__":
    main()