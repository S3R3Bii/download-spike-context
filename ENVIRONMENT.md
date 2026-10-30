# Reproduction environment

Source acquisition and initial calculation: CPython 3.10.11, Requests 2.32.3. Independent arithmetic uses SQLite JSON1/calendar joins and Decimal at precision 80; source-original reconstruction is a separate path. Figures use Matplotlib 3.10.9. PDF extraction uses pypdf 6.10.0 under the bundled CPython 3.12.14 runtime; the manuscript is built with Tectonic and rendered by Poppler.

Public replay uses a full-history Git clone, Requests for collector fixtures, standard-library numerical/source replay and an output directory outside the checkout. It never invokes source acquisition. No package statistics refresh, download log query, account, key, BigQuery execution or paid service is needed. New runtime receipts do not replace original measurements.
