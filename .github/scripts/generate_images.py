# generate_images.py
import os
import re
import requests
import base64
import yaml
from pathlib import Path

# --- Configuration ---
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
API_URL = "https://api.together.xyz/inference"
# Verify this is the correct model identifier you want to use
MODEL = "black-forest-labs/FLUX.1-schnell-Free"

# Ensure these paths match your repository structure exactly
POSTS_DIR = Path("content/blogs")
IMAGES_DIR = Path("static/images/blog")

HEADERS = {
    "Authorization": f"Bearer {TOGETHER_API_KEY}",
    "Content-Type": "application/json"
}

# Customize this prompt template if desired
PROMPT_TEMPLATE = "Create an abstract, aesthetically striking image representing: '{title}'"
# --- End Configuration ---

def generate_image(prompt: str) -> bytes:
    """Generates an image using the Together AI API."""
    if not TOGETHER_API_KEY:
        raise ValueError("TOGETHER_API_KEY environment variable not set.")

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "n": 1,             # Ensure we ask for 1 image
        "steps": 30,        # Adjust steps as needed for quality/speed
        "width": 512,       # Specify width
        "height": 512,      # Specify height
        # Add other parameters supported by the model/API if needed
    }
    print(f"Sending request to Together API for prompt: '{prompt}'")
    response = requests.post(API_URL, headers=HEADERS, json=payload)

    try:
        response.raise_for_status()  # Raises HTTPError for bad responses (4XX, 5XX)
    except requests.exceptions.RequestException as e:
        print(f"API Request failed: {e}")
        print(f"Response Status Code: {response.status_code}")
        print(f"Response Body: {response.text}") # Log the response body for debugging
        raise

    result = response.json()

    # --- IMPORTANT ---
    # Verify the structure of the API response. The key 'image_base64' might be nested.
    # Example nested structure: result['output']['choices'][0]['image_base64']
    # If image generation fails, print the 'result' object below to inspect its structure.
    # print("API Response JSON:", result) # Uncomment for debugging
    # ---
    if "output" in result and "choices" in result["output"] and len(result["output"]["choices"]) > 0 and "image_base64" in result["output"]["choices"][0]:
         return base64.b64decode(result["output"]["choices"][0]["image_base64"])
    # Fallback check for a simpler structure, just in case
    elif "image_base64" in result:
         print("Warning: Using top-level 'image_base64'. Check if this is the intended API response structure.")
         return base64.b64decode(result["image_base64"])

    print("Error: Could not find 'image_base64' in the expected location in the API response.")
    print("API Response JSON:", result) # Print the structure if decoding failed
    raise RuntimeError("Image generation failed: 'image_base64' key not found in response.")


def parse_frontmatter(filepath: Path) -> dict:
    """Parses YAML frontmatter from a Markdown file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        # Regex to find content between '---' lines
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL | re.MULTILINE)
        if match:
            frontmatter_str = match.group(1)
            # Safely load the YAML content
            front = yaml.safe_load(frontmatter_str)
            return front if isinstance(front, dict) else {}
        return {}
    except FileNotFoundError:
        print(f"Warning: File not found {filepath}")
        return {}
    except yaml.YAMLError as e:
        print(f"Warning: Could not parse YAML frontmatter in {filepath}: {e}")
        return {}
    except Exception as e:
        print(f"Warning: Error reading or parsing {filepath}: {e}")
        return {}

def main():
    """Main function to find posts, generate missing images, and save them."""
    print(f"Starting image generation process.")
    print(f"Scanning posts in: {POSTS_DIR.resolve()}")
    print(f"Saving images to: {IMAGES_DIR.resolve()}")

    # Ensure the output directory exists
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    generated_count = 0
    skipped_count = 0
    failed_count = 0

    if not POSTS_DIR.is_dir():
        print(f"Error: Posts directory not found: {POSTS_DIR.resolve()}")
        return

    for md_file in POSTS_DIR.glob("*.md"):
        print(f"\nProcessing file: {md_file.name}")
        front = parse_frontmatter(md_file)
        if not front:
            print("  - No valid frontmatter found. Skipping.")
            skipped_count += 1
            continue

        # Check if 'featured_image' exists and if it points to the expected image dir
        image_path_str = front.get("featured_image", "")

        # --- Logic Check ---
        # This script currently ONLY generates images if the featured_image path
        # in the frontmatter starts EXACTLY with '/images/'.
        # Adjust this condition if your paths are structured differently
        # (e.g., relative paths 'images/blog/...' or absolute '/static/images/blog/...')
        if not image_path_str or not image_path_str.startswith("/images/blog/"):
             if not image_path_str:
                 print(f"  - No 'featured_image' key in frontmatter. Skipping.")
             else:
                print(f"  - 'featured_image' path ('{image_path_str}') does not start with '/images/blog/'. Skipping.")
             skipped_count += 1
             continue
        # --- End Logic Check ---


        # Construct the expected output path based on the filename in featured_image
        image_filename = Path(image_path_str).name
        image_out_path = IMAGES_DIR / image_filename

        if image_out_path.exists():
            print(f"  - Image already exists: {image_out_path}. Skipping.")
            skipped_count += 1
            continue

        # Get title for the prompt (use filename as fallback)
        title = front.get("title")
        if not title:
             # Create a title from filename (e.g., "my-cool-post.md" -> "my cool post")
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
            # Catch errors during generation or saving for this specific file
            print(f"  - FAILED to generate image for {md_file.name}: {e}")
            failed_count += 1
            # Optional: uncomment to stop the script on the first failure
            # raise

    print("\n--- Image Generation Summary ---")
    print(f"Generated: {generated_count}")
    print(f"Skipped (exists or no path): {skipped_count}")
    print(f"Failed: {failed_count}")
    print("------------------------------")

if __name__ == "__main__":
    main()