# .github/scripts/generate_images.py
import os
import re
import requests
import base64
import yaml
import time  # <-- Import the time module
from pathlib import Path

# --- Configuration ---
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
API_URL = "https://api.together.xyz/inference"
MODEL = "black-forest-labs/FLUX.1-schnell-Free"

POSTS_DIR = Path("content/blogs")
IMAGES_DIR = Path("static/images/blogs") # Plural 'blogs'

# Delay between API calls in seconds (to respect rate limits)
# 6 queries/min = 10 seconds/query. Add buffer -> 12 seconds.
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
        # *** FIX: Changed steps from 30 to 4 ***
        "steps": 4,
        "width": 512,
        "height": 512,
    }
    print(f"Sending request to Together API for prompt: '{prompt}'")
    response = requests.post(API_URL, headers=HEADERS, json=payload)

    try:
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        # Log details before raising the exception again
        print(f"API Request failed: {e}")
        try:
            # Try to get status code and body even on error
            print(f"Response Status Code: {response.status_code}")
            print(f"Response Body: {response.text}")
        except Exception:
             print("Could not retrieve response details after initial error.")
        raise # Re-raise the original exception to be caught in main()

    result = response.json()

    # Check common nested structure first
    if "output" in result and "choices" in result["output"] and len(result["output"]["choices"]) > 0 and "image_base64" in result["output"]["choices"][0]:
         return base64.b64decode(result["output"]["choices"][0]["image_base64"])
    elif "image_base64" in result: # Fallback check
         print("Warning: Using top-level 'image_base64'. Verify API response structure.")
         return base64.b64decode(result["image_base64"])

    print("Error: Could not find 'image_base64' in the expected location in the API response.")
    print("API Response JSON:", result)
    raise RuntimeError("Image generation failed: 'image_base64' key not found.")


def parse_frontmatter(filepath: Path) -> dict:
    """Parses YAML frontmatter from a Markdown file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL | re.MULTILINE)
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
    print(f"API call delay set to: {API_DELAY} seconds")

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    generated_count = 0
    skipped_count = 0
    failed_count = 0
    processed_count = 0 # Keep track for delaying

    if not POSTS_DIR.is_dir():
        print(f"Error: Posts directory not found: {POSTS_DIR.resolve()}")
        return

    # Get list of files first to know the total count if needed
    md_files = list(POSTS_DIR.glob("*.md"))
    total_files = len(md_files)
    print(f"Found {total_files} markdown files to process.")

    for md_file in md_files:
        processed_count += 1
        print(f"\nProcessing file {processed_count}/{total_files}: {md_file.name}")

        # --- Add delay *before* processing the next file (if not the first) ---
        # Ensures delay even if parsing/checks cause a skip before API call
        if processed_count > 1:
             print(f"  - Waiting {API_DELAY} seconds before next API interaction...")
             time.sleep(API_DELAY)
        # ---

        front = parse_frontmatter(md_file)
        if not front:
            print("  - No valid frontmatter found. Skipping.")
            skipped_count += 1
            continue

        image_path_str = front.get("featured_image", "")

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
            img_data = generate_image(prompt)
            with open(image_out_path, "wb") as img_file:
                img_file.write(img_data)
            print(f"  - Successfully generated and saved image: {image_out_path}")
            generated_count += 1
        except Exception as e:
            # Catch errors during generation or saving
            # Error details should have been printed within generate_image()
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