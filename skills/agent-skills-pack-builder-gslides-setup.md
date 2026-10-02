---
title: Google Slides API Setup and Basic Operations
agents: [builder]
tags: [google-slides, api-setup, authentication, utility]
---
This skill provides foundational utilities for authenticating with the Google Slides API and performing basic slide operations. It serves as a prerequisite for higher-level skills like building sales decks or adding data visualizations.

## Capabilities
- Authenticate using service account credentials (JSON)
- Refresh access tokens automatically
- Create new presentations
- Retrieve presentation metadata
- Add slides with specified layouts
- Insert text into slide placeholders
- Read existing slide content

## Prerequisites
- Google Cloud project with Google Slides API and Google Drive API enabled
- Service account with domain-wide delegation (if accessing user drives) or appropriate OAuth scopes
- Service account credentials JSON file

## Configuration
The skill expects the following environment variables or secrets:
- `GOOGLE_SERVICE_ACCOUNT_JSON`: Path to or contents of service account key file
- `GOOGLE_SLIDES_SCOPES`: Optional, defaults to `['https://www.googleapis.com/auth/presentations', 'https://www.googleapis.com/auth/drive.file']`

## Core Functions
### authenticate()
Returns authorized Google Slides and Drive service objects.

### create_presentation(title: str) -> dict
Creates a new presentation with the given title.
Returns: `{presentationId: str, presentationUrl: str}`

### get_presentation(presentation_id: str) -> dict
Fetches the full presentation JSON.

### add_slide(presentation_id: str, slide_index: int, layout: str) -> dict
Inserts a slide at the specified index with the given layout (e.g., 'TITLE_AND_BODY', 'SECTION_HEADER').
Returns the object ID of the new slide.

### insert_text(presentation_id: str, object_id: str, text: str, index: int = 0) -> dict
Inserts text into a shape identified by object_id at the specified index (0-based).

### batch_update(presentation_id: str, requests: list) -> dict
Executes a list of Google Slides API batchUpdate requests.

## Usage Example
```python
# Initialize the skill
gs_skill = load_skill("agent-skills-pack-builder-gslides-setup")

# Authenticate
slides_service, drive_service = gs_skill.authenticate()

# Create a presentation
pres = gs_skill.create_presentation("My Sales Deck")
pres_id = pres['presentationId']

# Add a title slide
slide = gs_skill.add_slide(pres_id, 0, 'TITLE')
title_id = slide['objectIds'][0]

# Add title text
gs_skill.insert_text(pres_id, title_id, "Quarterly Business Review")

# Add a content slide
gs_skill.add_slide(pres_id, 1, 'TITLE_AND_BODY')
```

## Error Handling
- Raises `AuthenticationError` if credentials are invalid or missing
- Raises `APIError` for non-2xx responses from Google APIs
- Implements exponential backoff for rate limit errors (429)