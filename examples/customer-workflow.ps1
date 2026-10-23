# Editable example: all acquisition, calculations and validation remain in the engine.
# Run from the checkout. Replace nonsecret values and use a new destination per capture.
$toolkitPython = '.\.venv\Scripts\python.exe'
$profileAlias = 'lab'
$workDirectory = '.private\customer-example'
# First use: enroll once with hidden input in your own terminal.
# & $toolkitPython -m le_results.cli auth set --profile $profileAlias
& $toolkitPython -m le_results.cli doctor --profile $profileAlias
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $toolkitPython -m le_results.cli discover --profile $profileAlias --test-type LoadTest --limit 20 --out "$workDirectory\discovery.json"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# Review discovered IDs before uncommenting selected capture and reporting commands.
# & $toolkitPython -m le_results.cli select --test-type LoadTest --id 'REPLACE_WITH_UUID' --out "$workDirectory\selection.json"
# & $toolkitPython -m le_results.cli export --profile $profileAlias --selection "$workDirectory\selection.json" --max-requests 200 --max-pages 10 --out "$workDirectory\capture"
# & $toolkitPython -m le_results.cli verify "$workDirectory\capture"
# & $toolkitPython -m le_results.cli compare --baseline "$workDirectory\baseline" --candidate "$workDirectory\candidate" --config "$workDirectory\comparison-config.json" --out "$workDirectory\comparison.json"
# & $toolkitPython -m le_results.cli report --comparison "$workDirectory\comparison.json" --config examples\report.json --out "$workDirectory\snapshot"
# & $toolkitPython -m le_results.cli report-live --config "$workDirectory\live-report.json" --out "$workDirectory\live-report"

# Wider existing Continuous screening (bounded, read-only):
# & $toolkitPython -m le_results.cli recommend --profile $profileAlias --limit 100 --candidates 5 --continuous-candidates 40 --out "$workDirectory\recommendations.json"
# Single result/window without a comparison:
# & $toolkitPython -m le_results.cli report-capture --capture "$workDirectory\capture" --out "$workDirectory\finite"
# Copy examples/continuous-selected-report.json and resolve its one ID/window/metric before generation.
# & $toolkitPython -m le_results.cli report-live --config "$workDirectory\live-selection.json" --out "$workDirectory\live-selected"
# Existing native Application GET PDF; use an explicit completed Application UUID:
# & $toolkitPython -m le_results.cli download-pdf --profile $profileAlias --application-run-id 'REPLACE_WITH_UUID' --out "$workDirectory\application.pdf"
# Optional file-only destination preparation, no database writes:
# & $toolkitPython -m le_results.cli export-line-protocol --capture "$workDirectory\capture" --out "$workDirectory\line-protocol"
