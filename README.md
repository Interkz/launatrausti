# Launatrausti

Icelandic salary transparency platform - like [levels.fyi](https://levels.fyi) but using public data from annual reports.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Seed with sample data (for testing)
python scripts/seed_sample.py

# Run the web server
uvicorn src.main:app --reload

# Open http://localhost:8000
```

## Processing Real PDFs

1. Download annual reports from [Skatturinn](https://www.skatturinn.is/fyrirtaekjaskra/leit)
2. Save PDFs to the `pdfs/` folder
3. Set your Anthropic API key:
   ```bash
   export ANTHROPIC_API_KEY=your-key-here
   ```
4. Extract data:
   ```bash
   python scripts/extract_pdf.py pdfs/your-report.pdf --kennitala 1234567890
   ```

## Project Structure

```
launatrausti/
├── src/
│   ├── main.py          # FastAPI web app
│   ├── database.py      # SQLite database layer
│   ├── extractor.py     # PDF extraction with Claude
│   └── templates/       # HTML templates
├── scripts/
│   ├── extract_pdf.py   # CLI for processing PDFs
│   └── seed_sample.py   # Add test data
├── pdfs/                # Put annual report PDFs here
├── data-sources/        # Research on data sources
└── launatrausti.db      # SQLite database (auto-created)
```

## How It Works

1. **Data Source**: Annual reports (ársreikningar) filed with Skatturinn
2. **Extraction**: pdfplumber + Claude API parses PDF text
3. **Calculation**: `Average Salary = Launakostnaður / Meðalfjöldi starfsmanna`
4. **Display**: FastAPI serves ranked company list

## API Endpoints

- `GET /` - Web UI with rankings
- `GET /company/{id}` - Company detail page
- `GET /api/companies?year=2023` - JSON API
- `GET /api/company/{id}` - Company JSON

## Data Fields

| Field | Icelandic | Description |
|-------|-----------|-------------|
| Wage costs | Launakostnaður | Total salary expenses |
| Employees | Meðalfjöldi starfsmanna | Average headcount |
| Revenue | Tekjur | Total revenue (optional) |

## Deploy to Vercel

1. Install Vercel CLI:
   ```bash
   npm install -g vercel
   ```

2. Make sure you have data in the database:
   ```bash
   python scripts/seed_sample.py
   ```

3. Deploy:
   ```bash
   vercel
   ```

4. For production deployment:
   ```bash
   vercel --prod
   ```

**Note:** The SQLite database is bundled with the deployment. Data is read-only on Vercel (writes won't persist). For a production app with write capabilities, consider using [Turso](https://turso.tech/) (SQLite-compatible edge database).

## Limitations

- Average salary includes ALL employees (CEO to intern)
- Part-time workers may skew the average
- Benefits/bonuses may or may not be included
- Data is 6-12 months behind (annual reports)

## License

MIT
