---
title: Build B2B Sales Deck in Google Slides
agents: [builder]
tags: [google-slides, sales-deck, b2b, enterprise]
---
This skill enables an agent to generate a professional enterprise B2B sales deck using the Google Slides API. The deck follows best practices: one idea per slide, numerical evidence on almost every slide, narrative flow (problem → changes → proof → ask), and concise slide copy suitable for verbal presentation.

## Prerequisites
- Google Cloud project with Google Slides API enabled
- Service account credentials (JSON) stored securely
- The agent must have access to the credentials (via environment variable or secure secret storage)

## Inputs
- `presentation_title`: Title for the Google Slides presentation
- `slide_content`: Structured array of slide objects, each containing:
  - `title`: Slide title (string)
  - `bullet_points`: Array of concise bullet points (strings)
  - `number`: Optional numerical datum to highlight (string or number)
  - `slide_type`: Optional layout specifier (e.g., "TITLE_AND_BODY", "SECTION_HEADER")

## Outputs
- Creates a new Google Slides presentation in the user's Google Drive
- Returns the presentation URL and ID

## Usage Example
```python
# Pseudocode for agent usage
slides_skill = load_skill("agent-skills-pack-builder-gslides-sales-deck")
presentation = slides_skill.build_deck(
    presentation_title="Q3 AcmeCo Solutions Overview",
    slide_content=[
        {
            "title": "The Cost of Inaction",
            "bullet_points": [
                "Manual processes cause 20% revenue leakage annually",
                "Competitors adopting automation gain 15% market share YoY"
            ],
            "number": "$2.3M",
            "slide_type": "SECTION_HEADER"
        },
        {
            "title": "Our Solution",
            "bullet_points": [
                "End-to-end automation platform",
                "Seamless ERP/CRM integration",
                "Real-time analytics dashboard"
            ],
            "number": "5x ROI",
            "slide_type": "TITLE_AND_BODY"
        }
    ]
)
print(f"Deck created: {presentation['url']}")
```

## Implementation Notes
- Uses Google Slides API REST endpoints via HTTP requests
- Handles authentication via service account JWT flow
- Implements retry logic for rate limits
- Validates slide content against enterprise deck rubric before creation