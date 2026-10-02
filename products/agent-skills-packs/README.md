# Agent Skills Pack: Google Slides Sales Deck Builder

This pack contains three complementary skills for creating enterprise B2B sales decks in Google Slides using the Kiraci agent system.

## Skills Included

1. **agent-skills-pack-builder-gslides-sales-deck** - Builds a complete sales deck following enterprise best practices
2. **agent-skills-pack-builder-gslides-setup** - Handles Google Slides API authentication and basic operations
3. **agent-skills-pack-builder-gslides-data-viz** - Adds data visualizations and formats numbers for impact

## Installation

To install this skill pack into your Kiraci instance:

1. Copy the three `.md` files from this pack into the `skills/` directory of your Kiraci workspace
2. Restart the Kiraci agent system (if running) to load the new skills
3. The skills will be available for use by builder agents

## Usage Example

```python
# Load the skills
setup_skill = load_skill("agent-skills-pack-builder-gslides-setup")
deck_skill = load_skill("agent-skills-pack-builder-gslides-sales-deck")
viz_skill = load_skill("agent-skills-pack-builder-gslides-data-viz")

# Authenticate and create presentation
slides_service, drive_service = setup_skill.authenticate()
presentation = setup_skill.create_presentation("Q3 Sales Review")

# Build the deck structure
deck = deck_skill.build_deck(
    presentation_title="Q3 Sales Review",
    slide_content=[...]  # Define your slide content
)

# Enhance with data visualizations
enhanced = viz_skill.enhance_presentation(
    presentation_id=presentation['presentationId'],
    data_sources=[...]   # Define your charts and data
)

print(f"Sales deck ready: {enhanced['url']}")
```

## Requirements

- Kiraci agent system v0.2+
- Google Cloud project with Slides API enabled
- Service account credentials for authentication
- Python 3.11+ with required dependencies (google-api-python-client, etc.)

## License

MIT License - see individual skill files for details.