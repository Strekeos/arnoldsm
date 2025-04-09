import os
import re
import requests
import base64
import yaml
from pathlib import Path

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
API_URL = "https://api.together.xyz/inference"
MODEL = "togethercomputer/flux-schnell"

POSTS_DIR = Path("content/blogs")
IMAGES_DIR = Path("static/images/blog")

HEADERS = {
    "Authorization": f"Bearer {TOGETHER_API_KEY}",
    "Content-Type": "application/json"
}

PROMPT_TEMPLATE = "Create an abstract, aesthetically striking image representing: '{title}'"


def generate_image(prompt: str) -> bytes:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "steps": 30,
        "size": "512x512"
    }
    response = requests.post(API_URL, headers=HEADERS, json=payload)
    response.raise_for_status()
    result = response.json()
    if "image_base64" in result:
        return base64.b64decode(result["image_base64"])
    raise RuntimeError("Image generation failed")


def parse_frontmatter(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.match(r"---\n(.*?)\n---\n", content, re.DOTALL)
    if match:
        front = yaml.safe_load(match.group(1))
        return front
    return {}


def main():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    for md_file in POSTS_DIR.glob("*.md"):
        front = parse_frontmatter(md_file)
        if not front:
            continue

        image_path = front.get("featured_image", "")
        if not image_path.startswith("/images/"):
            continue

        image_name = Path(image_path).name
        image_out = IMAGES_DIR / image_name

        if image_out.exists():
            print(f"Image already exists: {image_out}")
            continue

        title = front.get("title") or md_file.stem.replace("-", " ")
        prompt = PROMPT_TEMPLATE.format(title=title)
        print(f"Generating image for '{title}' -> {image_name}")
        try:
            img_data = generate_image(prompt)
            with open(image_out, "wb") as img_file:
                img_file.write(img_data)
            print(f"Saved to {image_out}")
        except Exception as e:
            print(f"Failed for {md_file.name}: {e}")


if __name__ == "__main__":
    main()
