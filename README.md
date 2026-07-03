# Excel to PowerPoint Generator

Generates professional McKinsey-grade PowerPoint presentations from application data domain mapping Excel files.

## Requirements

**Conservative, Bank-Approved Libraries Only:**

| Library | Version | Purpose |
|---------|---------|---------|
| openpyxl | >= 3.0.0 | Pure Python Excel reader |
| python-pptx | >= 0.6.21 | Pure Python PowerPoint generator |

Both libraries are:
- Pure Python (no C extensions requiring compilation)
- Widely used in enterprise environments
- No external network dependencies
- Open source with permissive licenses

## Installation

```bash
pip install -r requirements.txt
```

Or install directly:

```bash
pip install openpyxl python-pptx
```

## Usage

```bash
python excel_to_ppt.py <input.xlsx> [output.pptx]
```

**Examples:**

```bash
# Basic usage (output will be input_presentation.pptx)
python excel_to_ppt.py application_data.xlsx

# Specify output file
python excel_to_ppt.py application_data.xlsx Q3_Data_Domain_Report.pptx
```

## Required Excel Columns

Your Excel file must contain these columns (case-insensitive, partial matches accepted):

| Column Name | Description |
|-------------|-------------|
| `DATA DOMAIN FULL` | Primary grouping level |
| `SUB-DATA DOMAIN` | Secondary grouping level |
| `SUB-SUB-DATA DOMAIN` | Tertiary grouping level |
| `ACTIVITY` | Activity classification |
| `Host Application Code` | Application identifier |
| `Application Name` | Application display name |
| `Application Hosting Country` | Country code/name |
| `LOBT` | Line of Business/Technology |

## Output Structure

The generated presentation contains:

1. **Title Slide** - Professional cover page with generation date
2. **Executive Summary** - Overview statistics and domain table
3. **Domain Sections** - For each DATA DOMAIN FULL:
   - Section divider slide (blue background)
   - Sub-domain content slides with application tables

## Presentation Features

- **Professional Design**: McKinsey-inspired color palette (dark blue, white, gray)
- **Consistent Formatting**: Standardized headers, footers, and typography
- **Pagination**: Auto-splits large tables across multiple slides (max 12 rows/slide)
- **Footer**: Page numbers and confidentiality notice on every slide

## Testing

Generate and test with sample data:

```bash
python create_sample_data.py  # Creates sample_data.xlsx
python excel_to_ppt.py sample_data.xlsx test_output.pptx
```

## Troubleshooting

| Error | Solution |
|-------|----------|
| `ModuleNotFoundError: openpyxl` | Run `pip install openpyxl` |
| `ModuleNotFoundError: pptx` | Run `pip install python-pptx` |
| `WARNING: Could not find columns` | Check Excel column names match expected names |
| `No data found` | Ensure Excel has data rows below header row |

## License

MIT License - Free to use and modify.
