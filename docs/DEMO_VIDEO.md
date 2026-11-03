# Demo video script (about 90 seconds)

Record at 1080p with the browser zoomed to ~125% so SQL is readable. Windows: Win+G (Game Bar) or OBS. Keep the terminal font large. Do one take per scene and cut; no music needed.

| Time | On screen | Say (plain, one idea each) |
|---|---|---|
| 0:00-0:10 | The app's home page | "This is a text-to-SQL assistant over a music store database. It runs a small open model locally, no paid API." |
| 0:10-0:30 | Click an example, then show SQL, the receipt, and the table | "It shows the SQL it wrote, what the checks did, and the rows. I can read the query before trusting the answer." |
| 0:30-0:50 | Type `Delete all customers` (instant refusal), then `Get rid of every invoice` (not caught by the wording check, so the model writes a DELETE and the parser blocks it: the page shows "SQL the model wrote (not run)") | "Two layers. A wording check refuses obvious write requests. If a paraphrase gets past it, the model's DELETE is stopped by a parser before it reaches the database, and the connection is read-only anyway." |
| 0:45-1:00 | Ask a hard question the model gets wrong (pick one from `results/` failures) | "It is not perfect. On hard questions it is wrong about four times in ten. That is why the project measures it." |
| 1:00-1:20 | Terminal: `python -m eval.report --split test` | "143 hand-written questions, a held-out test set run once. Execution accuracy compares result sets. Bigger model helped significantly; prompt tricks did not." |
| 1:20-1:30 | README results section | "Code, tests, CI and the full study are on GitHub." |

Verify the second prompt behaves as described before recording (the model's output can vary). Before recording: run `python -m eval.export_demo`, start the app, and ask the example questions once so the model is warm.
