import os
import glob
import yaml
import logging
import requests
from typing import List, Dict
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
# Retrieve API key from environment variable (updated requirement)
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Relative paths rooted at arnoldsm project folder (updated requirement)
CONTENT_DIR = os.path.join("..", "arnoldsm", "content", "blogs")
IMAGES_DIR = os.path.join("..", "arnoldsm", "static", "images", "blogs")

def parse_frontmatter(md_content):
    """
    Parse YAML frontmatter from markdown content.
    Returns a dict of frontmatter fields.
    """
    if not md_content.startswith('---'):
        return {}
    try:
        parts = md_content.split('---', 2)
        if len(parts) < 3:
            return {}
        frontmatter = yaml.safe_load(parts[1])
        return frontmatter if isinstance(frontmatter, dict) else {}
    except yaml.YAMLError as e:
        logging.error(f"YAML parsing error: {e}")
        return {}

def generate_simple_images(prompt: str, model: str = "black-forest-labs/FLUX.1-schnell-Free", steps: int = 4, n: int = 4) -> List[str]:
    """
    Generate images using the Together SDK.
    Returns a list of image base64 strings or URLs.
    """
    try:
        from together import Together
    except ImportError:
        logging.error("Together SDK is not installed. Please install with 'pip install together'")
        return []

    images = []
    try:
        client = Together(api_key=TOGETHER_API_KEY)  # Use environment variable API key (updated)
        for i in range(n):
            try:
                response = client.images.generate(
                    prompt=prompt,
                    model=model,
                    steps=steps,
                    n=1  # Request only 1 image per call
                )
                for item in response.data:
                    if hasattr(item, 'b64_json') and item.b64_json:
                        images.append(item.b64_json)
                    elif hasattr(item, 'url') and item.url:
                        images.append(item.url)
                logging.info(f"[SDK] Generated image {i+1}/{n} for prompt: {prompt}")
            except Exception as e:
                logging.error(f"[SDK] Image generation failed on attempt {i+1}: {e}")
    except Exception as e:
        logging.error(f"[SDK] Error initializing Together client: {e}")

    return images

# Removed UI-related imports (tkinter, PIL, io, webbrowser) as per user request
import base64

# Removed select_images_ui() function and all UI logic as per user request

def check_image_exists(image_path):
    """
    Check if the image file exists in the images directory.
    """
    return os.path.isfile(image_path)

def main():
    """
    Batch process markdown files to generate missing images.
    - Scans markdown files in CONTENT_DIR.
    - Extracts prompt from frontmatter.
    - Checks if image exists in IMAGES_DIR.
    - If missing, generates image and saves it.
    - Non-interactive, suitable for automation.
    """

    FORCE_REGENERATE = os.getenv("FORCE_REGENERATE", "0") == "1"
    logging.info(f"FORCE_REGENERATE is {'enabled' if FORCE_REGENERATE else 'disabled'}.")

    if not TOGETHER_API_KEY:
        logging.warning("TOGETHER_API_KEY not found in environment variables.")
        return

    # Ensure output directory exists
    os.makedirs(IMAGES_DIR, exist_ok=True)

    # Find all markdown files recursively
    md_files = glob.glob(os.path.join(CONTENT_DIR, "**", "*.md"), recursive=True)
    logging.info(f"Found {len(md_files)} markdown files to process.")

    for md_path in md_files:
        logging.info(f"Processing markdown file: {md_path}")
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logging.error(f"Failed to read {md_path}: {e}")
            continue

        frontmatter = parse_frontmatter(content)
        if not frontmatter:
            logging.info(f"No frontmatter found in {md_path}, skipping.")
            continue

        # Extract prompt from frontmatter
        prompt = frontmatter.get("prompt")
        if not prompt:
            logging.info(f"No prompt found in {md_path}, skipping.")
            continue

        # Determine output image filename (same as markdown filename but .jpg)
        md_filename = os.path.splitext(os.path.basename(md_path))[0]
        image_filename = f"{md_filename}.jpg"
        image_path = os.path.join(IMAGES_DIR, image_filename)

        # Check if image already exists
        if os.path.isfile(image_path):
            if not FORCE_REGENERATE:
                logging.info(f"Image already exists for {md_filename}, skipping generation.")
                continue
            else:
                logging.info(f"Image already exists for {md_filename}, but FORCE_REGENERATE is enabled. Regenerating image.")

        # Generate image
        logging.info(f"Generating image for {md_filename} with prompt: {prompt}")
        images = generate_simple_images(prompt, n=1)

        if images:
            save_image(images[0], image_path)
            logging.info(f"Saved generated image to {image_path}")
        else:
            logging.warning(f"No image generated for {md_filename}")

    logging.info("Batch image generation complete.")

# Removed unused save_all_images() function as per user request

def save_image(image_data: str, save_path: str):
    """
    Save an image from base64 string or URL to the specified path as JPEG.
    """
    try:
        # Check if image_data is a URL
        if image_data.startswith('http://') or image_data.startswith('https://'):
            response = requests.get(image_data, timeout=15)
            response.raise_for_status()
            img_bytes = response.content
        else:
            # Assume base64 string
            img_bytes = base64.b64decode(image_data)

        # Save image bytes to file
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, 'wb') as f:
            f.write(img_bytes)
        logging.info(f"Saved image to {save_path}")

    except Exception as e:
        logging.error(f"Failed to save image to {save_path}: {e}")

if __name__ == "__main__":
    main()