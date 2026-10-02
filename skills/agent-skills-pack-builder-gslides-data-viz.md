---
title: Add Data Visualizations and Format Numbers for Slides
agents: [builder]
tags: [google-slides, data-viz, charts, formatting, numbers]
---
This skill enhances existing Google Slides presentations by adding data visualizations (charts, graphs) and formatting numerical content according to enterprise presentation standards. It ensures numbers are prominent, easy to read, and visually supported.

## Capabilities
- Format numerical text with thousand separators, decimal places, and currency symbols
- Create bar charts, line charts, and pie charts from provided data
- Insert charts into slides as images or native Google Slides charts
- Highlight key numbers with color, size, or callout shapes
- Generate simple inline sparklines for trends
- Apply consistent number formatting across all slides in a deck

## Prerequisites
- Google Slides API access (via authentication skill or service account)
- Data to visualize: arrays of numbers, labels, or structured datasets
- Basic slide deck already created (use the sales deck skill or setup skill first)

## Inputs
- `presentation_id`: ID of the target Google Slides presentation
- `data_sources`: Array of data objects, each containing:
  - `type`: "bar", "line", "pie", "metric", or "table"
  - `title`: Chart title (string)
  - `data`: Numerical data appropriate to chart type
  - `options`: Formatting options (currency, decimal places, etc.)
  - `target_slide_index`: Slide index where the visualization should be placed
  - `position`: Optional {x, y, width, height} in points
- `number_format_rules`: Global formatting rules for numbers in text (e.g., currency: "USD", decimals: 2)

## Outputs
- Modified presentation with charts inserted and numbers formatted
- Returns updated presentation URL

## Usage Example
```python
# Load the skill
viz_skill = load_skill("agent-skills-pack-builder-gslides-data-viz")

# Sample data for a bar chart showing Q3 sales by region
sales_data = {
    "type": "bar",
    "title": "Q3 Sales by Region (USD Millions)",
    "data": {
        "labels": ["North", "South", "East", "West"],
        "datasets": [{
            "label": "Sales",
            "data": [12.5, 8.3, 15.2, 11.7]
        }]
    },
    "options": {
        "currency": "USD",
        "decimalPlaces": 1
    },
    "target_slide_index": 2  # Third slide
}

# Apply the enhancement
result = viz_skill.enhance_presentation(
    presentation_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
    data_sources=[sales_data],
    number_format_rules={"currency": "USD", "decimalPlaces": 0}
)

print(f"Enhanced deck: {result['url']}")
```

## Chart Generation Process
1. Data validation and normalization
2. Chart rendering using matplotlib (headless) to PNG
3. Upload PNG to Google Drive as blob
4. Insert image into slide at specified position
5. Alternative: Use Google Slides chart API for native charts (when available)

## Number Formatting Rules
- Automatically detects numbers in slide text (using regex)
- Applies formatting: `¥1,234.56` or `45.6%`
- Preserves non-numeric text and formatting
- Skips numbers inside code blocks or preformatted text (if detectable)

## Limitations
- Chart generation requires matplotlib installed in the agent environment
- Native Google Slides chart insertion depends on API availability
- Large datasets may be downsampled for readability