import os
from openai import OpenAI, APIError, AuthenticationError, RateLimitError
import yaml
import datetime
import pytz
from slugify import slugify
from dotenv import load_dotenv
import logging
import sys
import re # Import regex for checking AI terms

# --- Configuration ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = "google/gemini-2.5-pro-exp-03-25:free" # Use the model confirmed earlier
INPUT_TITLE = os.environ.get("POST_TITLE_INPUT", "").strip() # Get input, default empty, strip whitespace
INPUT_TOPIC = os.environ.get("POST_TOPIC_INPUT", "").strip() # Get input, default empty, strip whitespace
OUTPUT_DIR = os.path.join("content", "blogs")
YOUR_SITE_URL = os.environ.get("YOUR_SITE_URL")
YOUR_APP_NAME = os.environ.get("YOUR_APP_NAME")

# --- Helper Functions --- (generate_filename, get_current_datetime_str remain the same)
def generate_filename(title):
    """Creates a slugified, unique filename."""
    base_slug = slugify(title) if title else "untitled-post" # Handle empty title case
    potential_filename = os.path.join(OUTPUT_DIR, f"{base_slug}.md")
    counter = 1
    while os.path.exists(potential_filename):
        potential_filename = os.path.join(OUTPUT_DIR, f"{base_slug}-{counter}.md")
        counter += 1
    return potential_filename

def get_current_datetime_str():
    """Gets the current datetime in Europe/Istanbul timezone (ISO format)."""
    try:
        utc_now = datetime.datetime.now(pytz.utc)
        istanbul_tz = pytz.timezone('Europe/Istanbul')
        istanbul_now = utc_now.astimezone(istanbul_tz)
        return istanbul_now.isoformat()
    except Exception as e:
        logging.error(f"Failed to get Istanbul time: {e}. Falling back to UTC.")
        return datetime.datetime.now(pytz.utc).isoformat()

# --- NEW: Function to get AI Client (avoids redundant code) ---
def get_ai_client():
    """Initializes and returns the OpenAI client configured for OpenRouter."""
    if not API_KEY:
        logging.error("OPENROUTER_API_KEY is not set.")
        return None
    default_headers = {}
    if YOUR_SITE_URL:
        default_headers["HTTP-Referer"] = YOUR_SITE_URL
    if YOUR_APP_NAME:
        default_headers["X-Title"] = YOUR_APP_NAME
    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=API_KEY,
            default_headers=default_headers if default_headers else None
        )
        return client
    except Exception as e:
        logging.error(f"Failed to initialize AI client: {e}")
        return None

# --- NEW: Function to Generate Only a Topic ---
def generate_topic_only(client):
    """Calls AI to generate a blog topic, avoiding AI subjects."""
    if not client: return None
    logging.info("Attempting to generate a blog topic (non-AI)...")
    try:
        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": "You suggest interesting and engaging blog post topics."},
                {"role": "user", "content": "Suggest one single, specific, interesting blog post topic. Avoid topics related to AI, artificial intelligence, machine learning, LLMs, or the tech industry itself. Focus on culture, history, science, nature, arts, or human interest."}
            ],
            temperature=0.8,
            max_tokens=50,
            n=1,
            stop=None,
        )
        # --- ADD DETAILED LOGGING ---
        logging.debug(f"Raw response object from topic generation: {response}")
        # --- / ADD DETAILED LOGGING ---

        if response.choices:
            topic = response.choices[0].message.content.strip().strip('"').strip('.')
            # --- Log the topic *before* the check ---
            logging.info(f"AI suggested topic raw content: '{topic}'") # Log with quotes to see if truly empty
            # --- / ---
            if topic: # Check if the topic is not empty
                if not re.search(r'\b(ai|artificial intelligence|machine learning|llm)\b', topic, re.IGNORECASE):
                    logging.info(f"Using valid topic: {topic}")
                    return topic
                else:
                    logging.warning(f"AI generated an AI topic despite instructions: {topic}.")
                    return None
            else:
                # Explicitly log that the content was empty
                logging.warning("AI response content for topic was empty.")
                return None
        else:
            logging.warning("AI response object had no 'choices'.")
            return None
    except Exception as e:
        logging.error(f"Error during topic generation: {e}")
        return None

# --- NEW: Function to Generate Only a Title ---
def generate_title_only(client, topic):
    """Calls AI to generate a title based on a given topic."""
    if not client: return None
    logging.info(f"Attempting to generate a title for topic: {topic}")

    # Check if the provided topic is about AI - needed for title generation instruction
    is_ai_topic = bool(re.search(r'\b(ai|artificial intelligence|machine learning|llm)\b', topic, re.IGNORECASE))
    ai_mention_instruction = "Do not mention AI unless the topic explicitly requires it." if not is_ai_topic else ""

    try:
        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": "You are skilled at writing compelling, SEO-friendly blog post titles."},
                {"role": "user", "content": f"Generate one compelling and SEO-friendly blog post title (no extra text or quotes) for the topic: '{topic}'. {ai_mention_instruction}"}
            ],
            temperature=0.7,
            max_tokens=30,
            n=1,
            stop=None,
        )
        if response.choices:
            title = response.choices[0].message.content.strip().strip('"')
            logging.info(f"AI suggested title: {title}")
            return title
        else:
            logging.warning("AI did not provide a title suggestion.")
            return None
    except Exception as e:
        logging.error(f"Error during title generation: {e}")
        return None


# --- Modified AI Call Function for Content ---
def call_ai_for_content(client, title, topic, user_requested_ai_topic):
    """Calls the AI API using the OpenAI library structure, requesting SEO optimization."""
    if not client: return None, None # Check if client initialization failed

    # --- Adjust prompts based on whether the user originally asked for AI topic ---
    ai_mention_instruction = "Do NOT mention AI, artificial intelligence, or machine learning unless the user's original topic explicitly required it." if not user_requested_ai_topic else "You can mention AI/ML concepts as relevant to the user-provided AI topic."

    system_prompt = f"""
    You are an AI assistant specialized in creating high-quality, SEO-optimized blog posts formatted in Markdown.
    Your goal is to generate informative, engaging content that ranks well in search engines.
    Follow the requested structure precisely.
    Generate the requested frontmatter fields based *only* on the content you write.
    Ensure keywords are used naturally, not stuffed. Write for humans first, search engines second.
    {ai_mention_instruction}
    Do NOT include the --- separators or the fixed frontmatter fields (title, date, layout, draft, featured, featured_image) in your response.
    Your entire response should start directly with the 'tags:' line and continue with the rest of the requested frontmatter and then the markdown body (starting with '## Introduction').
    """

    user_prompt = f"""
    Generate an SEO-optimized markdown blog post draft.

    Blog Post Title: "{title}"
    Blog Post Topic/Keywords: "{topic}"

    Instructions:
    1.  Incorporate relevant keywords from the 'Topic/Keywords' naturally throughout the headings and body text.
    2.  Write clear, concise, and compelling headings that include relevant keywords where appropriate.
    3.  Structure the content logically to satisfy user search intent for the given topic.
    4.  Ensure the body text is well-written, informative, engaging, and provides value to the reader. Use markdown formatting (like bolding, lists) where appropriate.
    5.  {ai_mention_instruction}

    Required Structure:
    1.  ## Introduction: Introduce the topic, its importance, and hook the reader. Include primary keywords early.
    2.  ## [Generate SEO-friendly Heading 1]: Discuss the first key aspect, incorporating keywords.
    3.  ## [Generate SEO-friendly Heading 2]: Discuss the second key aspect, incorporating keywords.
    4.  ## [Generate SEO-friendly Heading for Analysis/Implications]: Provide deeper analysis or context, using relevant terms.
    5.  ## Conclusion: Summarize key takeaways and offer a final thought. Reinforce primary keywords if natural.

    Required Frontmatter fields to generate (based on the content you write):
    - tags: ["List", "of", "5-7", "relevant", "SEO-friendly", "tags"]
    - categories: ["Primary", "relevant", "SEO-friendly", "Category"]
    - description: "A concise, compelling meta description (1-2 sentences, ~155 characters) summarizing the post and including primary keywords. Suitable for search engine results."
    - suggested_prompt: "A detailed image generation prompt relevant to the blog post content and title."

    Begin your response directly with 'tags:'.
    """

    logging.info(f"Sending SEO-focused request via OpenAI library to OpenRouter (Model: {OPENROUTER_MODEL}) for title: {title}")

    try:
        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
        )
        # ... (response parsing logic remains the same as before) ...
        if response.choices:
            ai_response_text = response.choices[0].message.content.strip()
            if "## Introduction" not in ai_response_text:
                 logging.error("AI response structure error: '## Introduction' marker missing.")
                 body_start_index = ai_response_text.find('##')
                 if body_start_index != -1:
                      generated_frontmatter_str = ai_response_text[:body_start_index].strip()
                      generated_body = ai_response_text[body_start_index:].strip()
                 else: return None, None
            else:
                 parts = ai_response_text.split('## Introduction', 1)
                 generated_frontmatter_str = parts[0].strip()
                 generated_body = "## Introduction" + parts[1].strip()
            try:
                ai_generated_frontmatter = yaml.safe_load(generated_frontmatter_str)
                if not isinstance(ai_generated_frontmatter, dict):
                     lines = generated_frontmatter_str.split('\n')
                     temp_dict = {}
                     for line in lines:
                          if ':' in line:
                               key, val = line.split(':', 1)
                               temp_dict[key.strip().lower()] = val.strip().strip('"').strip("'")
                     if temp_dict: ai_generated_frontmatter = temp_dict
                     else: raise ValueError("Parsed frontmatter not dict/lines.")
                else: ai_generated_frontmatter = {k.lower(): v for k, v in ai_generated_frontmatter.items()}
                return ai_generated_frontmatter, generated_body
            except (yaml.YAMLError, ValueError, TypeError) as e:
                 logging.error(f"Could not parse AI-generated frontmatter: {e}")
                 return None, None
        else: return None, None
    except (AuthenticationError, RateLimitError, APIError, Exception) as e:
        logging.error(f"Error during AI content call: {e}")
        return None, None


# --- Main Execution Logic ---
if __name__ == "__main__":
    logging.info("Starting blog post generation script...")
    final_filename = ""
    ai_client = get_ai_client() # Initialize client once

    if not ai_client:
        logging.error("Failed to initialize AI client. Exiting.")
        print(f"markdown_filename=") # Output empty filename
        sys.exit(1)

    # --- Determine Final Title and Topic ---
    final_title = INPUT_TITLE
    final_topic = INPUT_TOPIC
    user_requested_ai_topic = bool(INPUT_TOPIC and re.search(r'\b(ai|artificial intelligence|machine learning|llm)\b', INPUT_TOPIC, re.IGNORECASE))

    if not final_topic:
        logging.info("Topic input is blank. Generating topic...")
        final_topic = generate_topic_only(ai_client)
        if not final_topic:
             logging.error("Failed to generate a topic. Exiting.")
             print(f"markdown_filename=")
             sys.exit(1)
        # Since topic was blank, the generated topic is guaranteed non-AI, so user_requested_ai_topic remains False.

    if not final_title:
        logging.info("Title input is blank. Generating title...")
        # Pass the determined final_topic (could be original or generated)
        final_title = generate_title_only(ai_client, final_topic)
        if not final_title:
             logging.warning("Failed to generate a title. Using topic as fallback title.")
             final_title = final_topic # Use topic as title if generation fails

    logging.info(f"Proceeding with Title: '{final_title}' and Topic: '{final_topic}'")
    logging.info(f"User requested AI topic explicitly: {user_requested_ai_topic}")

    # --- Ensure output directory exists ---
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
    except OSError as e:
        logging.error(f"Cannot create output directory {OUTPUT_DIR}: {e}")
        print(f"markdown_filename=")
        sys.exit(1)

    # --- Generate the main content ---
    ai_frontmatter, ai_body = call_ai_for_content(ai_client, final_title, final_topic, user_requested_ai_topic)

    # --- Assemble and save the file ---
    if ai_frontmatter and ai_body:
        logging.info("Constructing final markdown file...")
        final_frontmatter = {
            'title': final_title, # Use the final determined title
            'date': get_current_datetime_str(),
            'layout': 'single',
            'draft': True,
            'featured': False,
            'featured_image': '',
            'tags': ai_frontmatter.get('tags', []),
            'categories': ai_frontmatter.get('categories', []),
            'description': ai_frontmatter.get('description', ''),
            'suggested_prompt': ai_frontmatter.get('suggested_prompt', '')
        }
        if isinstance(final_frontmatter['tags'], str):
            final_frontmatter['tags'] = [tag.strip() for tag in final_frontmatter['tags'].split(',')]
        if isinstance(final_frontmatter['categories'], str):
             final_frontmatter['categories'] = [cat.strip() for cat in final_frontmatter['categories'].split(',')]

        final_filename = generate_filename(final_frontmatter['title'])
        logging.info(f"Generated filename: {final_filename}")
        try:
            final_frontmatter_yaml = yaml.dump(final_frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=None, width=1000)
        except Exception as e:
             logging.error(f"Failed to dump final frontmatter to YAML: {e}")
             print(f"filename=")
             sys.exit(1)
        final_content = f"---\n{final_frontmatter_yaml.strip()}\n---\n\n{ai_body}\n"
        try:
            with open(final_filename, "w", encoding="utf-8") as f:
                f.write(final_content)
            logging.info(f"Successfully wrote blog post draft to: {final_filename}")
        except IOError as e:
            logging.error(f"Failed to write file {final_filename}: {e}")
            final_filename = ""
            print(f"filename=")
            sys.exit(1)
    else:
        logging.error("Failed to get valid content from AI. No file generated.")
        final_filename = ""

    # --- Output filename for workflow ---
    print(f"markdown_filename={final_filename}")
    logging.info("Blog post generation script finished.")
