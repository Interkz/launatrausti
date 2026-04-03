# Session Summary — 2026-04-03

## What Was Done

### Shipped (5 commits, all pushed to master)
- **New front page:** "Hvað viltu þéna?" salary search hero with percentile position bar, occupation matches, "Næsta stig" aspirational hook, job matches, company matches
- **Backend fixes:** `get_companies_near_salary()`, `get_all_occupations_flat()`, `source_pdf` in ranked query, budget-line filtering
- **Education backfill:** 22 → 101 jobs with `education_required` via keyword heuristic
- **Alfred scraper rewrite:** Switched to public Next.js data routes with minimal metadata storage + link-back
- **SEO meta tags:** Company pages now have "Laun hjá [company]" titles, og:description with real salary data, canonical URLs
- **Benchmarks page:** Fully translated to Icelandic, broken CSS vars fixed
- **Footer:** Translated to Icelandic
- **CLAUDE.md restructure:** 440 → 96 lines. Reference material moved to `docs/ai/reference.md`. Added 4 guardrails including mandatory Codex review gate.
- **Global CLAUDE.md:** Fixed confidence/verification tension, added process respect rule
- **Codex CLI:** Installed (v0.118.0), authenticated with Emil's Codex Plus subscription

### Research Completed
- **Alfred.is legality:** ToS prohibits scraping but is browse-wrap (likely unenforceable). CV-Online precedent supports our use. Minimal metadata + link-back is defensible.
- **Keldan API:** Structured financials but no launakostnaður field. "Internal use only" terms. PDF download endpoint is the useful part.
- **CreditInfo:** Has launakostnaður + starfsmenn as structured data, 600K+ reports. But same "no redistribution" terms.
- **Tekjur.is history:** Published individual income, shut down in 48 days by Persónuvernd. Journalism exemption is the key distinction.
- **Skatturinn tax data:** Physical-only, digitizing ruled illegal. Tekjublaðið does manual transcription.
- **Ja.is Gagnatorg:** Real API at `gagnatorg.ja.is`, full company registry, 30-day free trial.
- **Union surveys:** VFÍ (engineers), SSF (financial sector), FVH (business grads), gogn.fjr.is (government) — all have scrapeable salary data beyond VR.
- **Glassdoor/levels.fyi:** Crowdsourcing won't work at Iceland's scale. Our public filings data is the advantage. Employer branding is the revenue model.

## Files Changed
```
CLAUDE.md                     | 349 lines trimmed
docs/ai/reference.md          | 111 lines (new)
launatrausti.db               | education backfill
scripts/scrape_jobs.py        | Alfred scraper rewrite
src/database.py               | new helpers, budget filter, flat query
src/main.py                   | salary search route, next_tier
src/templates/base.html       | hero CSS, position bar, next-tier styles, footer
src/templates/benchmarks.html | full Icelandic translation
src/templates/company.html    | SEO meta tags
src/templates/index.html      | complete front page rewrite
```

## Issues Found
- **Zero private sector data.** All 205 annual reports are public sector. "Einkageirinn" tab is empty.
- **Skatturinn PDF scraper violates their TOS.** 115 failures, can't legally use it.
- **66% of job salary estimates are national_avg placeholders.** Most estimates are decorative.
- **VR comparison math bug:** `diff_pct` on company pages computed against monthly VR avg instead of annualized. Needs fixing.

## What Remains (approved plan)
- [ ] Kill `/launaleynd` (misleading premise)
- [ ] Merge `/company/{id}/financials` content into `/company/{id}`, then delete route
- [ ] Fix VR comparison math bug
- [ ] Clean `/salaries` page (dirty categories, English labels)
- [ ] Rename rankings to "Opinber fyrirtæki", remove empty Einkageirinn tab
- [ ] Update nav to 6 items

## Blockers
- **Private sector data:** Waiting for Tuesday (April 8) to email Skatturinn + Keldan + Alfred
- **Ja.is Gagnatorg:** Emil needs to sign up for 30-day trial
- **Tax data journalism route:** Needs media lawyer consultation + Fjölmiðlanefnd registration before August 2026

## Decisions Made
- **Codex review is now mandatory** before proposing page deletions, scraper rewrites, or product pivots
- **CLAUDE.md restructured** to separate behavioral rules from reference material
- **Confidence doctrine changed** from "never hedge" to "never waffle, never bluff — confidence earned by checking"
- **Alfred jobs:** Keep showing with link-back attribution. Contact Alfred about partnership.
- **Rankings stay** on front page (SEO/discovery value). Just be honest about public sector only.
- **`/salaries` stays** — different data source (VR surveys) from `/samanburdur` (Hagstofa occupations)

## Emails to Send Tuesday
1. **Skatturinn:** Request formal bulk access to annual report data/PDFs
2. **Keldan (Kristófer):** Ask about PDF download endpoint terms specifically
3. **Alfred.is:** Propose partnership (our salary data ↔ their job listings)
