"""Hand-written gold questions for Chinook. Edit here, then run `python -m eval.build_gold`.

Each entry: (category, difficulty, question, gold_sql, ordered, limit_key)
  ordered:   True if row ORDER matters for correctness (top-N / explicit ranking questions)
  limit_key: index of the ORDER BY column in the result, used to verify there is no tie at the LIMIT boundary
Question text names the output columns whenever more than one column is expected, so the answer shape is unambiguous.
"""

GOLD = []


def q(cat, diff, question, sql, ordered=False, limit_key=None):
    GOLD.append((cat, diff, question, " ".join(sql.split()), ordered, limit_key))


# ------------------------------------------------------------------ EASY
q("aggregate", "easy", "How many artists are there?", "SELECT COUNT(*) FROM Artist")
q("aggregate", "easy", "How many tracks are in the database?", "SELECT COUNT(*) FROM Track")
q("filter", "easy", "List the names of all genres.", "SELECT Name FROM Genre")
q("filter", "easy", "How many customers are from Brazil?", "SELECT COUNT(*) FROM Customer WHERE Country = 'Brazil'")
q("filter", "easy", "List the names of all media types.", "SELECT Name FROM MediaType")
q("filter", "easy", "What is the title of the album with AlbumId 10?", "SELECT Title FROM Album WHERE AlbumId = 10")
q("aggregate", "easy", "How many employees are there?", "SELECT COUNT(*) FROM Employee")
q("filter", "easy", "List the first and last names of employees whose title is 'Sales Support Agent'.",
  "SELECT FirstName, LastName FROM Employee WHERE Title = 'Sales Support Agent'")
q("filter", "easy", "How many tracks have a unit price greater than 0.99?", "SELECT COUNT(*) FROM Track WHERE UnitPrice > 0.99")
q("aggregate", "easy", "How many distinct countries do customers come from?", "SELECT COUNT(DISTINCT Country) FROM Customer")
q("aggregate", "easy", "How many distinct playlist names exist?", "SELECT COUNT(DISTINCT Name) FROM Playlist")
q("aggregate", "easy", "What is the sum of all invoice totals?", "SELECT SUM(Total) FROM Invoice")
q("aggregate", "easy", "What is the average invoice total?", "SELECT AVG(Total) FROM Invoice")
q("aggregate", "easy", "What is the longest track length in milliseconds?", "SELECT MAX(Milliseconds) FROM Track")
q("string", "easy", "List the names of artists whose name starts with 'Z'.", "SELECT Name FROM Artist WHERE Name LIKE 'Z%'")
q("filter", "easy", "How many customers have no company listed?", "SELECT COUNT(*) FROM Customer WHERE Company IS NULL")
q("filter", "easy", "List the email addresses of customers in Canada.", "SELECT Email FROM Customer WHERE Country = 'Canada'")
q("filter", "easy", "How many invoices were billed to Germany?", "SELECT COUNT(*) FROM Invoice WHERE BillingCountry = 'Germany'")
q("aggregate", "easy", "What is the smallest file size in bytes among all tracks?", "SELECT MIN(Bytes) FROM Track")
q("aggregate", "easy", "How many albums are there?", "SELECT COUNT(*) FROM Album")
q("filter", "easy", "List the distinct cities where employees are based.", "SELECT DISTINCT City FROM Employee")
q("filter", "easy", "How many tracks have a composer listed?", "SELECT COUNT(*) FROM Track WHERE Composer IS NOT NULL")
q("topn", "easy", "Which employee was hired first? Return first name and last name.",
  "SELECT FirstName, LastName FROM Employee ORDER BY HireDate LIMIT 1", True)
q("filter", "easy", "How many invoices have a total greater than 10?", "SELECT COUNT(*) FROM Invoice WHERE Total > 10")
q("filter", "easy", "List the first and last names of customers whose last name is 'Brown'.",
  "SELECT FirstName, LastName FROM Customer WHERE LastName = 'Brown'")
q("aggregate", "easy", "How many invoice lines does invoice 100 have?", "SELECT COUNT(*) FROM InvoiceLine WHERE InvoiceId = 100")
q("string", "easy", "How many tracks have 'Love' in their name?", "SELECT COUNT(*) FROM Track WHERE Name LIKE '%Love%'")
q("string", "easy", "How many customers have a gmail.com email address?", "SELECT COUNT(*) FROM Customer WHERE Email LIKE '%@gmail.com'")
q("date", "easy", "How many employees were hired in 2003 or later?", "SELECT COUNT(*) FROM Employee WHERE HireDate >= '2003-01-01'")
q("date", "easy", "How many invoices were issued in 2023?", "SELECT COUNT(*) FROM Invoice WHERE strftime('%Y', InvoiceDate) = '2023'")

# ------------------------------------------------------------------ MEDIUM: joins
q("join", "medium", "List the titles of all albums by the artist 'AC/DC'.",
  "SELECT Album.Title FROM Album JOIN Artist ON Album.ArtistId = Artist.ArtistId WHERE Artist.Name = 'AC/DC'")
q("join", "medium", "How many tracks are on the album titled 'Let There Be Rock'?",
  "SELECT COUNT(*) FROM Track JOIN Album ON Track.AlbumId = Album.AlbumId WHERE Album.Title = 'Let There Be Rock'")
q("join", "medium", "List the names of all tracks in the genre 'Jazz'.",
  "SELECT Track.Name FROM Track JOIN Genre ON Track.GenreId = Genre.GenreId WHERE Genre.Name = 'Jazz'")
q("join", "medium", "What is the name of the artist who made the album 'Big Ones'?",
  "SELECT Artist.Name FROM Artist JOIN Album ON Artist.ArtistId = Album.ArtistId WHERE Album.Title = 'Big Ones'")
q("join", "medium", "List the names of tracks in the playlist named 'Grunge'.",
  "SELECT Track.Name FROM Track JOIN PlaylistTrack ON Track.TrackId = PlaylistTrack.TrackId JOIN Playlist ON PlaylistTrack.PlaylistId = Playlist.PlaylistId WHERE Playlist.Name = 'Grunge'")
q("join", "medium", "How many customers are supported by the employee Jane Peacock?",
  "SELECT COUNT(*) FROM Customer JOIN Employee ON Customer.SupportRepId = Employee.EmployeeId WHERE Employee.FirstName = 'Jane' AND Employee.LastName = 'Peacock'")
q("join", "medium", "List the distinct names of media types used by tracks in the genre 'Opera'.",
  "SELECT DISTINCT MediaType.Name FROM MediaType JOIN Track ON MediaType.MediaTypeId = Track.MediaTypeId JOIN Genre ON Track.GenreId = Genre.GenreId WHERE Genre.Name = 'Opera'")
q("join", "medium", "List the track names and album titles for tracks composed by 'Jimi Hendrix'. Return track name and album title.",
  "SELECT Track.Name, Album.Title FROM Track JOIN Album ON Track.AlbumId = Album.AlbumId WHERE Track.Composer = 'Jimi Hendrix'")
q("join", "medium", "How much has the customer Frank Harris spent in total across all invoices?",
  "SELECT SUM(Invoice.Total) FROM Invoice JOIN Customer ON Invoice.CustomerId = Customer.CustomerId WHERE Customer.FirstName = 'Frank' AND Customer.LastName = 'Harris'")
q("join", "medium", "What is the total revenue from tracks in the genre 'Rock'? Revenue is UnitPrice times Quantity from invoice lines.",
  "SELECT SUM(InvoiceLine.UnitPrice * InvoiceLine.Quantity) FROM InvoiceLine JOIN Track ON InvoiceLine.TrackId = Track.TrackId JOIN Genre ON Track.GenreId = Genre.GenreId WHERE Genre.Name = 'Rock'")
q("join", "medium", "List the first and last names of employees who report to Nancy Edwards.",
  "SELECT e.FirstName, e.LastName FROM Employee e JOIN Employee m ON e.ReportsTo = m.EmployeeId WHERE m.FirstName = 'Nancy' AND m.LastName = 'Edwards'")
q("join", "medium", "List each employee's first and last name together with their manager's first and last name, for employees who have a manager. Return employee first name, employee last name, manager first name, manager last name.",
  "SELECT e.FirstName, e.LastName, m.FirstName, m.LastName FROM Employee e JOIN Employee m ON e.ReportsTo = m.EmployeeId")
q("join", "medium", "How many distinct customers have purchased at least one track from the genre 'Latin'?",
  "SELECT COUNT(DISTINCT Invoice.CustomerId) FROM Invoice JOIN InvoiceLine ON Invoice.InvoiceId = InvoiceLine.InvoiceId JOIN Track ON InvoiceLine.TrackId = Track.TrackId JOIN Genre ON Track.GenreId = Genre.GenreId WHERE Genre.Name = 'Latin'")
q("join", "medium", "What is the total duration in minutes of the album titled 'Presence'? Divide milliseconds by 60000.0.",
  "SELECT SUM(Track.Milliseconds) / 60000.0 FROM Track JOIN Album ON Track.AlbumId = Album.AlbumId WHERE Album.Title = 'Presence'")
q("join", "medium", "List the distinct billing countries of invoices for customers supported by Steve Johnson.",
  "SELECT DISTINCT Invoice.BillingCountry FROM Invoice JOIN Customer ON Invoice.CustomerId = Customer.CustomerId JOIN Employee ON Customer.SupportRepId = Employee.EmployeeId WHERE Employee.FirstName = 'Steve' AND Employee.LastName = 'Johnson'")
q("join", "medium", "How many playlists contain at least one track by the artist 'Metallica'?",
  "SELECT COUNT(DISTINCT PlaylistTrack.PlaylistId) FROM PlaylistTrack JOIN Track ON PlaylistTrack.TrackId = Track.TrackId JOIN Album ON Track.AlbumId = Album.AlbumId JOIN Artist ON Album.ArtistId = Artist.ArtistId WHERE Artist.Name = 'Metallica'")

# ------------------------------------------------------------------ MEDIUM: group / having / top-n
q("group", "medium", "How many tracks are in each genre? Return genre name and track count.",
  "SELECT Genre.Name, COUNT(*) FROM Track JOIN Genre ON Track.GenreId = Genre.GenreId GROUP BY Genre.GenreId, Genre.Name")
q("group", "medium", "What is the total of invoice totals for each billing country? Return country and total.",
  "SELECT BillingCountry, SUM(Total) FROM Invoice GROUP BY BillingCountry")
q("group", "medium", "How many customers does each support representative have? Return rep first name, last name, and customer count.",
  "SELECT Employee.FirstName, Employee.LastName, COUNT(*) FROM Customer JOIN Employee ON Customer.SupportRepId = Employee.EmployeeId GROUP BY Employee.EmployeeId, Employee.FirstName, Employee.LastName")
q("group", "medium", "How many tracks does each media type have? Return media type name and track count.",
  "SELECT MediaType.Name, COUNT(*) FROM Track JOIN MediaType ON Track.MediaTypeId = MediaType.MediaTypeId GROUP BY MediaType.MediaTypeId, MediaType.Name")
q("group", "medium", "What is the average track length in milliseconds for each genre? Return genre name and average.",
  "SELECT Genre.Name, AVG(Track.Milliseconds) FROM Track JOIN Genre ON Track.GenreId = Genre.GenreId GROUP BY Genre.GenreId, Genre.Name")
q("group", "medium", "What is the total invoice revenue for each year? Return the year and total.",
  "SELECT strftime('%Y', InvoiceDate), SUM(Total) FROM Invoice GROUP BY strftime('%Y', InvoiceDate)")
q("group", "medium", "How many invoices does each customer have? Return CustomerId and invoice count.",
  "SELECT CustomerId, COUNT(*) FROM Invoice GROUP BY CustomerId")
q("group", "medium", "For the artist 'Led Zeppelin', how many tracks does each album have? Return album title and track count.",
  "SELECT Album.Title, COUNT(*) FROM Album JOIN Artist ON Album.ArtistId = Artist.ArtistId JOIN Track ON Track.AlbumId = Album.AlbumId WHERE Artist.Name = 'Led Zeppelin' GROUP BY Album.AlbumId, Album.Title")
q("group", "medium", "What is the maximum track length in milliseconds in each genre? Return genre name and maximum.",
  "SELECT Genre.Name, MAX(Track.Milliseconds) FROM Track JOIN Genre ON Track.GenreId = Genre.GenreId GROUP BY Genre.GenreId, Genre.Name")
q("group", "medium", "How many invoices were issued in each month of 2023? Return month (YYYY-MM) and count.",
  "SELECT strftime('%Y-%m', InvoiceDate), COUNT(*) FROM Invoice WHERE strftime('%Y', InvoiceDate) = '2023' GROUP BY strftime('%Y-%m', InvoiceDate)")
q("having", "medium", "Which countries have more than 5 customers? Return country and customer count.",
  "SELECT Country, COUNT(*) FROM Customer GROUP BY Country HAVING COUNT(*) > 5")
q("having", "medium", "Which albums have more than 20 tracks? Return album title and track count.",
  "SELECT Album.Title, COUNT(*) FROM Album JOIN Track ON Track.AlbumId = Album.AlbumId GROUP BY Album.AlbumId, Album.Title HAVING COUNT(*) > 20")
q("having", "medium", "Which composers have more than 50 tracks? Return composer and track count.",
  "SELECT Composer, COUNT(*) FROM Track WHERE Composer IS NOT NULL GROUP BY Composer HAVING COUNT(*) > 50")
q("having", "medium", "Which artists have at least 10 albums? Return artist name and album count.",
  "SELECT Artist.Name, COUNT(*) FROM Artist JOIN Album ON Artist.ArtistId = Album.ArtistId GROUP BY Artist.ArtistId, Artist.Name HAVING COUNT(*) >= 10")
q("having", "medium", "Which customers have spent more than 40 in total? Return first name, last name, and total spent.",
  "SELECT Customer.FirstName, Customer.LastName, SUM(Invoice.Total) FROM Customer JOIN Invoice ON Customer.CustomerId = Invoice.CustomerId GROUP BY Customer.CustomerId, Customer.FirstName, Customer.LastName HAVING SUM(Invoice.Total) > 40")
q("having", "medium", "For billing countries with at least 5 invoices, what is the average invoice total? Return country and average.",
  "SELECT BillingCountry, AVG(Total) FROM Invoice GROUP BY BillingCountry HAVING COUNT(*) >= 5")
q("topn", "medium", "Which 5 genres have the most tracks? Return genre name and track count, highest first.",
  "SELECT Genre.Name, COUNT(*) AS c FROM Track JOIN Genre ON Track.GenreId = Genre.GenreId GROUP BY Genre.GenreId, Genre.Name ORDER BY c DESC LIMIT 5", True, 1)
q("topn", "medium", "Who are the top 5 customers by total spending? Return first name, last name, and total spent, highest first.",
  "SELECT Customer.FirstName, Customer.LastName, SUM(Invoice.Total) AS s FROM Customer JOIN Invoice ON Customer.CustomerId = Invoice.CustomerId GROUP BY Customer.CustomerId, Customer.FirstName, Customer.LastName ORDER BY s DESC LIMIT 5", True, 2)
q("topn", "medium", "Which 3 billing countries have the highest total invoice revenue? Return country and total, highest first.",
  "SELECT BillingCountry, SUM(Total) AS s FROM Invoice GROUP BY BillingCountry ORDER BY s DESC LIMIT 3", True, 1)
q("topn", "medium", "Which artist has the most albums? Return artist name and album count.",
  "SELECT Artist.Name, COUNT(*) AS c FROM Artist JOIN Album ON Artist.ArtistId = Album.ArtistId GROUP BY Artist.ArtistId, Artist.Name ORDER BY c DESC LIMIT 1", True, 1)
q("topn", "medium", "Which country has the most customers? Return country and customer count.",
  "SELECT Country, COUNT(*) AS c FROM Customer GROUP BY Country ORDER BY c DESC LIMIT 1", True, 1)
q("topn", "medium", "Which media type has the most tracks? Return media type name and track count.",
  "SELECT MediaType.Name, COUNT(*) AS c FROM Track JOIN MediaType ON Track.MediaTypeId = MediaType.MediaTypeId GROUP BY MediaType.MediaTypeId, MediaType.Name ORDER BY c DESC LIMIT 1", True, 1)
q("topn", "medium", "What are the 5 longest tracks? Return track name and length in milliseconds, longest first.",
  "SELECT Name, Milliseconds FROM Track ORDER BY Milliseconds DESC LIMIT 5", True, 1)
q("topn", "medium", "Which 2 employees were hired most recently? Return first name, last name, and hire date, most recent first.",
  "SELECT FirstName, LastName, HireDate FROM Employee ORDER BY HireDate DESC LIMIT 2", True, 2)
q("topn", "medium", "Which year had the highest total invoice revenue? Return the year and total.",
  "SELECT strftime('%Y', InvoiceDate) AS y, SUM(Total) AS s FROM Invoice GROUP BY y ORDER BY s DESC LIMIT 1", True, 1)
q("topn", "medium", "Which support representative's customers generated the most invoice revenue? Return first name, last name, and total revenue.",
  "SELECT Employee.FirstName, Employee.LastName, SUM(Invoice.Total) AS s FROM Employee JOIN Customer ON Customer.SupportRepId = Employee.EmployeeId JOIN Invoice ON Invoice.CustomerId = Customer.CustomerId GROUP BY Employee.EmployeeId, Employee.FirstName, Employee.LastName ORDER BY s DESC LIMIT 1", True, 2)

# ------------------------------------------------------------------ MEDIUM: negation / subquery / strings / dates / set ops
q("negation", "medium", "How many tracks have never been sold?", "SELECT COUNT(*) FROM Track WHERE TrackId NOT IN (SELECT TrackId FROM InvoiceLine)")
q("negation", "medium", "List the names of artists who have no albums.", "SELECT Name FROM Artist WHERE ArtistId NOT IN (SELECT ArtistId FROM Album)")
q("negation", "medium", "List the first and last names of employees who have no direct reports.",
  "SELECT FirstName, LastName FROM Employee WHERE EmployeeId NOT IN (SELECT ReportsTo FROM Employee WHERE ReportsTo IS NOT NULL)")
q("subquery", "medium", "Among genres that have at least one track, how many have fewer than 10 tracks?",
  "SELECT COUNT(*) FROM (SELECT GenreId FROM Track GROUP BY GenreId HAVING COUNT(*) < 10)")
q("subquery", "medium", "How many tracks are more expensive than the average track price?", "SELECT COUNT(*) FROM Track WHERE UnitPrice > (SELECT AVG(UnitPrice) FROM Track)")
q("subquery", "medium", "What is the second highest invoice total?", "SELECT MAX(Total) FROM Invoice WHERE Total < (SELECT MAX(Total) FROM Invoice)")
q("subquery", "medium", "List the names of tracks that are longer than the average track length.",
  "SELECT Name FROM Track WHERE Milliseconds > (SELECT AVG(Milliseconds) FROM Track)")
q("subquery", "medium", "How many invoices have a total above the average invoice total?", "SELECT COUNT(*) FROM Invoice WHERE Total > (SELECT AVG(Total) FROM Invoice)")
q("string", "medium", "List the titles of albums whose title contains 'Greatest Hits'.", "SELECT Title FROM Album WHERE Title LIKE '%Greatest Hits%'")
q("string", "medium", "How many artists have a name that contains the word 'Orchestra'?", "SELECT COUNT(*) FROM Artist WHERE Name LIKE '%Orchestra%'")
q("string", "medium", "List the first names of customers whose first name starts with 'J' and who live in the USA.",
  "SELECT FirstName FROM Customer WHERE FirstName LIKE 'J%' AND Country = 'USA'")
q("date", "medium", "List the first and last names of employees born before 1965.",
  "SELECT FirstName, LastName FROM Employee WHERE BirthDate < '1965-01-01'")
q("date", "medium", "What is the total invoice revenue in March 2023?",
  "SELECT SUM(Total) FROM Invoice WHERE strftime('%Y-%m', InvoiceDate) = '2023-03'")
q("date", "medium", "How many invoices were issued in the first quarter (January to March) of 2022?",
  "SELECT COUNT(*) FROM Invoice WHERE InvoiceDate >= '2022-01-01' AND InvoiceDate < '2022-04-01'")
q("setop", "medium", "List the names of genres that start with 'R' or contain the word 'Metal'. Return each name once.",
  "SELECT Name FROM Genre WHERE Name LIKE 'R%' UNION SELECT Name FROM Genre WHERE Name LIKE '%Metal%'")
q("setop", "medium", "Which countries appear both as a customer country and as an employee country?",
  "SELECT Country FROM Customer INTERSECT SELECT Country FROM Employee")
q("setop", "medium", "Which customer countries have no employee based in them?",
  "SELECT Country FROM Customer EXCEPT SELECT Country FROM Employee")

# ------------------------------------------------------------------ HARD: nested / cte / window / multi-condition
q("nested", "hard", "Which customers have spent more than the average total spending per customer? Return first name and last name.",
  "SELECT FirstName, LastName FROM Customer WHERE CustomerId IN (SELECT CustomerId FROM Invoice GROUP BY CustomerId HAVING SUM(Total) > (SELECT AVG(t) FROM (SELECT SUM(Total) AS t FROM Invoice GROUP BY CustomerId)))")
q("nested", "hard", "What is the average of the per-customer total spending?",
  "SELECT AVG(t) FROM (SELECT SUM(Total) AS t FROM Invoice GROUP BY CustomerId)")
q("nested", "hard", "Which customers have purchased tracks from both the 'Rock' and the 'Jazz' genres? Return first name and last name.",
  "SELECT Customer.FirstName, Customer.LastName FROM Customer JOIN Invoice ON Invoice.CustomerId = Customer.CustomerId JOIN InvoiceLine ON InvoiceLine.InvoiceId = Invoice.InvoiceId JOIN Track ON Track.TrackId = InvoiceLine.TrackId JOIN Genre ON Genre.GenreId = Track.GenreId WHERE Genre.Name IN ('Rock', 'Jazz') GROUP BY Customer.CustomerId, Customer.FirstName, Customer.LastName HAVING COUNT(DISTINCT Genre.Name) = 2")
q("nested", "hard", "Which artists have tracks in more than 3 different genres? Return artist name and genre count.",
  "SELECT Artist.Name, COUNT(DISTINCT Track.GenreId) FROM Artist JOIN Album ON Album.ArtistId = Artist.ArtistId JOIN Track ON Track.AlbumId = Album.AlbumId GROUP BY Artist.ArtistId, Artist.Name HAVING COUNT(DISTINCT Track.GenreId) > 3")
q("nested", "hard", "Which albums have a total duration longer than one hour? Return album title.",
  "SELECT Album.Title FROM Album JOIN Track ON Track.AlbumId = Album.AlbumId GROUP BY Album.AlbumId, Album.Title HAVING SUM(Track.Milliseconds) > 3600000")
q("nested", "hard", "Which customers have placed invoices in every year from 2021 through 2025? Return first name and last name.",
  "SELECT Customer.FirstName, Customer.LastName FROM Customer JOIN Invoice ON Invoice.CustomerId = Customer.CustomerId GROUP BY Customer.CustomerId, Customer.FirstName, Customer.LastName HAVING COUNT(DISTINCT strftime('%Y', Invoice.InvoiceDate)) = 5")
q("nested", "hard", "Which tracks appear in both the 'Classical' and the 'Classical 101 - Deep Cuts' playlists? Return track name.",
  "SELECT Track.Name FROM Track JOIN PlaylistTrack a ON a.TrackId = Track.TrackId JOIN Playlist pa ON pa.PlaylistId = a.PlaylistId JOIN PlaylistTrack b ON b.TrackId = Track.TrackId JOIN Playlist pb ON pb.PlaylistId = b.PlaylistId WHERE pa.Name = 'Classical' AND pb.Name = 'Classical 101 - Deep Cuts'")
q("nested", "hard", "How many tracks appear in more than one playlist?",
  "SELECT COUNT(*) FROM (SELECT TrackId FROM PlaylistTrack GROUP BY TrackId HAVING COUNT(DISTINCT PlaylistId) > 1)")
q("nested", "hard", "How many distinct customers bought tracks by more than 5 different artists?",
  "SELECT COUNT(*) FROM (SELECT Invoice.CustomerId FROM Invoice JOIN InvoiceLine ON InvoiceLine.InvoiceId = Invoice.InvoiceId JOIN Track ON Track.TrackId = InvoiceLine.TrackId JOIN Album ON Album.AlbumId = Track.AlbumId GROUP BY Invoice.CustomerId HAVING COUNT(DISTINCT Album.ArtistId) > 5)")
q("nested", "hard", "Which employees have supported customers who spent more than 100 in total across all of that employee's customers? Return first name and last name.",
  "SELECT Employee.FirstName, Employee.LastName FROM Employee JOIN Customer ON Customer.SupportRepId = Employee.EmployeeId JOIN Invoice ON Invoice.CustomerId = Customer.CustomerId GROUP BY Employee.EmployeeId, Employee.FirstName, Employee.LastName HAVING SUM(Invoice.Total) > 100")
q("cte", "hard", "What fraction of total invoice revenue comes from the USA? Return a single number between 0 and 1.",
  "SELECT SUM(CASE WHEN BillingCountry = 'USA' THEN Total ELSE 0 END) / SUM(Total) FROM Invoice")
q("cte", "hard", "For each year, what was the revenue and how did it compare to the previous year? Return year, revenue, and difference from previous year (NULL for the first year).",
  "WITH y AS (SELECT strftime('%Y', InvoiceDate) AS yr, SUM(Total) AS rev FROM Invoice GROUP BY yr) SELECT yr, rev, rev - LAG(rev) OVER (ORDER BY yr) FROM y")
q("cte", "hard", "For each genre, what percentage of all tracks does it hold? Return genre name and percentage (0-100).",
  "SELECT Genre.Name, COUNT(*) * 100.0 / (SELECT COUNT(*) FROM Track) FROM Track JOIN Genre ON Track.GenreId = Genre.GenreId GROUP BY Genre.GenreId, Genre.Name")
q("window", "hard", "Rank customers by total spending and return first name, last name, and rank for the top 3 ranks, using RANK so ties share a rank.",
  "WITH s AS (SELECT Customer.FirstName AS f, Customer.LastName AS l, SUM(Invoice.Total) AS t FROM Customer JOIN Invoice ON Customer.CustomerId = Invoice.CustomerId GROUP BY Customer.CustomerId, Customer.FirstName, Customer.LastName), r AS (SELECT f, l, RANK() OVER (ORDER BY t DESC) AS rk FROM s) SELECT f, l, rk FROM r WHERE rk <= 3", True)
q("window", "hard", "What is the single best-selling genre by revenue (UnitPrice times Quantity)? Return genre name and revenue.",
  "SELECT Genre.Name, SUM(InvoiceLine.UnitPrice * InvoiceLine.Quantity) AS r FROM InvoiceLine JOIN Track ON Track.TrackId = InvoiceLine.TrackId JOIN Genre ON Genre.GenreId = Track.GenreId GROUP BY Genre.GenreId, Genre.Name ORDER BY r DESC LIMIT 1", True, 1)
q("window", "hard", "What are the top 3 genres by revenue (UnitPrice times Quantity)? Return genre name and revenue, highest first.",
  "SELECT Genre.Name, SUM(InvoiceLine.UnitPrice * InvoiceLine.Quantity) AS r FROM InvoiceLine JOIN Track ON Track.TrackId = InvoiceLine.TrackId JOIN Genre ON Genre.GenreId = Track.GenreId GROUP BY Genre.GenreId, Genre.Name ORDER BY r DESC LIMIT 3", True, 1)
q("window", "hard", "Which artist's tracks have generated the most revenue (UnitPrice times Quantity)? Return artist name and revenue.",
  "SELECT Artist.Name, SUM(InvoiceLine.UnitPrice * InvoiceLine.Quantity) AS r FROM InvoiceLine JOIN Track ON Track.TrackId = InvoiceLine.TrackId JOIN Album ON Album.AlbumId = Track.AlbumId JOIN Artist ON Artist.ArtistId = Album.ArtistId GROUP BY Artist.ArtistId, Artist.Name ORDER BY r DESC LIMIT 1", True, 1)
q("window", "hard", "For each billing country, which customer spent the most? Return country, first name, last name. Assume no ties within a country.",
  "WITH s AS (SELECT Customer.CustomerId AS id, Customer.FirstName AS f, Customer.LastName AS l, Invoice.BillingCountry AS c, SUM(Invoice.Total) AS t FROM Customer JOIN Invoice ON Customer.CustomerId = Invoice.CustomerId GROUP BY Customer.CustomerId, Invoice.BillingCountry), r AS (SELECT c, f, l, ROW_NUMBER() OVER (PARTITION BY c ORDER BY t DESC) AS rn FROM s) SELECT c, f, l FROM r WHERE rn = 1")
q("nested", "hard", "How many customers have a total spending equal to or above the overall average invoice total times 8?",
  "SELECT COUNT(*) FROM (SELECT SUM(Total) AS t FROM Invoice GROUP BY CustomerId) WHERE t >= 8 * (SELECT AVG(Total) FROM Invoice)")
q("nested", "hard", "For each employee who has customers, what is the average invoice total across their customers' invoices? Return first name, last name, and average.",
  "SELECT Employee.FirstName, Employee.LastName, AVG(Invoice.Total) FROM Employee JOIN Customer ON Customer.SupportRepId = Employee.EmployeeId JOIN Invoice ON Invoice.CustomerId = Customer.CustomerId GROUP BY Employee.EmployeeId, Employee.FirstName, Employee.LastName")

# ------------------------------------------------------------------ STRESS TIER (appended after q109; ids stay stable)
q("compare", "hard", "How many customers live in a different country than their support representative?",
  "SELECT COUNT(*) FROM Customer JOIN Employee ON Customer.SupportRepId = Employee.EmployeeId WHERE Customer.Country <> Employee.Country")
q("negation", "hard", "How many customers have never purchased a track in the 'Jazz' genre?",
  "SELECT COUNT(*) FROM Customer WHERE CustomerId NOT IN (SELECT Invoice.CustomerId FROM Invoice JOIN InvoiceLine ON InvoiceLine.InvoiceId = Invoice.InvoiceId JOIN Track ON Track.TrackId = InvoiceLine.TrackId JOIN Genre ON Genre.GenreId = Track.GenreId WHERE Genre.Name = 'Jazz')")
q("nested", "hard", "Which customers have purchased tracks from at least 10 distinct genres? Return first name and last name.",
  "SELECT Customer.FirstName, Customer.LastName FROM Customer JOIN Invoice ON Invoice.CustomerId = Customer.CustomerId JOIN InvoiceLine ON InvoiceLine.InvoiceId = Invoice.InvoiceId JOIN Track ON Track.TrackId = InvoiceLine.TrackId GROUP BY Customer.CustomerId, Customer.FirstName, Customer.LastName HAVING COUNT(DISTINCT Track.GenreId) >= 10")
q("window", "hard", "For each month of 2023, what is the cumulative invoice revenue up to and including that month? Return month (YYYY-MM) and cumulative revenue.",
  "WITH m AS (SELECT strftime('%Y-%m', InvoiceDate) AS mo, SUM(Total) AS rev FROM Invoice WHERE strftime('%Y', InvoiceDate) = '2023' GROUP BY mo) SELECT mo, SUM(rev) OVER (ORDER BY mo) FROM m")
q("window", "hard", "For each month of 2024, what was the invoice revenue and the change from the previous month? Return month (YYYY-MM), revenue, and change (NULL for January).",
  "WITH m AS (SELECT strftime('%Y-%m', InvoiceDate) AS mo, SUM(Total) AS rev FROM Invoice WHERE strftime('%Y', InvoiceDate) = '2024' GROUP BY mo) SELECT mo, rev, rev - LAG(rev) OVER (ORDER BY mo) FROM m")
q("cte", "hard", "What is the median invoice total? If there is an even number of invoices, average the two middle values.",
  "SELECT AVG(Total) FROM (SELECT Total, ROW_NUMBER() OVER (ORDER BY Total) AS rn, COUNT(*) OVER () AS n FROM Invoice) WHERE rn IN ((n + 1) / 2, (n + 2) / 2)")
q("selfjoin", "hard", "How many unordered pairs of different customers live in the same city and country? Count each pair once.",
  "SELECT COUNT(*) FROM Customer a JOIN Customer b ON a.City = b.City AND a.Country = b.Country AND a.CustomerId < b.CustomerId")
q("selfjoin", "hard", "Which employees share their hire date with at least one other employee? Return first name and last name.",
  "SELECT a.FirstName, a.LastName FROM Employee a WHERE EXISTS (SELECT 1 FROM Employee b WHERE b.HireDate = a.HireDate AND b.EmployeeId <> a.EmployeeId)")
q("nested", "hard", "What is the maximum number of line items on any single invoice?",
  "SELECT MAX(c) FROM (SELECT COUNT(*) AS c FROM InvoiceLine GROUP BY InvoiceId)")
q("nested", "hard", "What is the largest number of distinct tracks purchased by any single customer?",
  "SELECT MAX(n) FROM (SELECT COUNT(DISTINCT InvoiceLine.TrackId) AS n FROM Invoice JOIN InvoiceLine ON InvoiceLine.InvoiceId = Invoice.InvoiceId GROUP BY Invoice.CustomerId)")
q("topn", "hard", "Which 3 genres have tracks by the largest number of distinct artists? Return genre name and artist count, highest first.",
  "SELECT Genre.Name, COUNT(DISTINCT Album.ArtistId) AS n FROM Genre JOIN Track ON Track.GenreId = Genre.GenreId JOIN Album ON Album.AlbumId = Track.AlbumId GROUP BY Genre.GenreId, Genre.Name ORDER BY n DESC LIMIT 3", True, 1)
q("date", "hard", "As of 2025-01-01, how many whole years had each employee worked? Compute it as the number of days since hire divided by 365.25, truncated. Return first name, last name, and years.",
  "SELECT FirstName, LastName, CAST((julianday('2025-01-01') - julianday(HireDate)) / 365.25 AS INTEGER) FROM Employee")
q("nested", "hard", "How many tracks were purchased by more than one different customer?",
  "SELECT COUNT(*) FROM (SELECT InvoiceLine.TrackId FROM InvoiceLine JOIN Invoice ON Invoice.InvoiceId = InvoiceLine.InvoiceId GROUP BY InvoiceLine.TrackId HAVING COUNT(DISTINCT Invoice.CustomerId) > 1)")
q("nested", "hard", "What is the average number of invoice lines per invoice?",
  "SELECT AVG(c) FROM (SELECT COUNT(*) AS c FROM InvoiceLine GROUP BY InvoiceId)")
q("cte", "hard", "What percentage of customers have spent more than 40 in total? Return a number from 0 to 100.",
  "SELECT 100.0 * SUM(CASE WHEN t > 40 THEN 1 ELSE 0 END) / COUNT(*) FROM (SELECT SUM(Total) AS t FROM Invoice GROUP BY CustomerId)")
q("setop", "hard", "How many customers have purchased at least one 'Latin' track but no 'Jazz' track?",
  "SELECT COUNT(*) FROM (SELECT Invoice.CustomerId FROM Invoice JOIN InvoiceLine ON InvoiceLine.InvoiceId = Invoice.InvoiceId JOIN Track ON Track.TrackId = InvoiceLine.TrackId JOIN Genre ON Genre.GenreId = Track.GenreId WHERE Genre.Name = 'Latin' EXCEPT SELECT Invoice.CustomerId FROM Invoice JOIN InvoiceLine ON InvoiceLine.InvoiceId = Invoice.InvoiceId JOIN Track ON Track.TrackId = InvoiceLine.TrackId JOIN Genre ON Genre.GenreId = Track.GenreId WHERE Genre.Name = 'Jazz')")
q("nested", "hard", "Which albums contain tracks from more than one genre? Return album title.",
  "SELECT Album.Title FROM Album JOIN Track ON Track.AlbumId = Album.AlbumId GROUP BY Album.AlbumId, Album.Title HAVING COUNT(DISTINCT Track.GenreId) > 1")
q("nested", "hard", "Which playlists contain tracks of more than 2 distinct media types? Return playlist name.",
  "SELECT Playlist.Name FROM Playlist JOIN PlaylistTrack ON PlaylistTrack.PlaylistId = Playlist.PlaylistId JOIN Track ON Track.TrackId = PlaylistTrack.TrackId GROUP BY Playlist.PlaylistId, Playlist.Name HAVING COUNT(DISTINCT Track.MediaTypeId) > 2")
q("group", "hard", "What was the total invoice revenue in 2023 for each support representative's customers? Return first name, last name, and revenue.",
  "SELECT Employee.FirstName, Employee.LastName, SUM(Invoice.Total) FROM Employee JOIN Customer ON Customer.SupportRepId = Employee.EmployeeId JOIN Invoice ON Invoice.CustomerId = Customer.CustomerId WHERE strftime('%Y', Invoice.InvoiceDate) = '2023' GROUP BY Employee.EmployeeId, Employee.FirstName, Employee.LastName")
q("topn", "hard", "Among billing countries with at least 5 invoices, which has the highest average invoice total? Return country and average.",
  "SELECT BillingCountry, AVG(Total) AS a FROM Invoice GROUP BY BillingCountry HAVING COUNT(*) >= 5 ORDER BY a DESC LIMIT 1", True, 1)
q("subquery", "hard", "How many tracks cost more than the average price of tracks in their own genre?",
  "SELECT COUNT(*) FROM Track t WHERE t.UnitPrice > (SELECT AVG(UnitPrice) FROM Track WHERE GenreId = t.GenreId)")
q("topn", "hard", "What are the 3 longest albums by total track duration? Return album title and total minutes (milliseconds divided by 60000.0), longest first.",
  "SELECT Album.Title, SUM(Track.Milliseconds) / 60000.0 AS m FROM Album JOIN Track ON Track.AlbumId = Album.AlbumId GROUP BY Album.AlbumId, Album.Title ORDER BY m DESC LIMIT 3", True, 1)
q("negation", "hard", "Which artists have albums but none of their tracks have ever been sold? Return artist name.",
  "SELECT Artist.Name FROM Artist WHERE EXISTS (SELECT 1 FROM Album WHERE Album.ArtistId = Artist.ArtistId) AND NOT EXISTS (SELECT 1 FROM Album JOIN Track ON Track.AlbumId = Album.AlbumId JOIN InvoiceLine ON InvoiceLine.TrackId = Track.TrackId WHERE Album.ArtistId = Artist.ArtistId)")
q("nested", "hard", "How many tracks appear on more than one invoice line?",
  "SELECT COUNT(*) FROM (SELECT TrackId FROM InvoiceLine GROUP BY TrackId HAVING COUNT(*) > 1)")
q("topn", "hard", "Which employee has the most direct reports? Return first name, last name, and the number of direct reports.",
  "SELECT m.FirstName, m.LastName, COUNT(*) AS n FROM Employee m JOIN Employee e ON e.ReportsTo = m.EmployeeId GROUP BY m.EmployeeId, m.FirstName, m.LastName ORDER BY n DESC LIMIT 1", True, 2)
q("nested", "hard", "What is the difference between the highest and the lowest yearly total invoice revenue?",
  "SELECT MAX(s) - MIN(s) FROM (SELECT SUM(Total) AS s FROM Invoice GROUP BY strftime('%Y', InvoiceDate))")
q("compare", "hard", "How many employees were hired before the manager they report to?",
  "SELECT COUNT(*) FROM Employee e JOIN Employee m ON e.ReportsTo = m.EmployeeId WHERE e.HireDate < m.HireDate")
q("join", "hard", "How many distinct composers have at least one track that has been sold?",
  "SELECT COUNT(DISTINCT Track.Composer) FROM Track JOIN InvoiceLine ON InvoiceLine.TrackId = Track.TrackId WHERE Track.Composer IS NOT NULL")
q("group", "hard", "For invoices issued in 2024, what is the average invoice total for customers billed in the USA versus all other countries? Return a label ('USA' or 'Other') and the average.",
  "SELECT CASE WHEN BillingCountry = 'USA' THEN 'USA' ELSE 'Other' END, AVG(Total) FROM Invoice WHERE strftime('%Y', InvoiceDate) = '2024' GROUP BY 1")
q("group", "hard", "For each support representative, how many distinct customers do they have and how many invoices do those customers have in total? Return first name, last name, customer count, and invoice count.",
  "SELECT Employee.FirstName, Employee.LastName, COUNT(DISTINCT Customer.CustomerId), COUNT(Invoice.InvoiceId) FROM Employee JOIN Customer ON Customer.SupportRepId = Employee.EmployeeId JOIN Invoice ON Invoice.CustomerId = Customer.CustomerId GROUP BY Employee.EmployeeId, Employee.FirstName, Employee.LastName")
q("selfjoin", "hard", "How many customers share their first name with at least one other customer?",
  "SELECT COUNT(*) FROM Customer c WHERE EXISTS (SELECT 1 FROM Customer d WHERE d.FirstName = c.FirstName AND d.CustomerId <> c.CustomerId)")
q("cte", "hard", "What fraction of tracks have been sold at least once? Return a number between 0 and 1.",
  "SELECT 1.0 * (SELECT COUNT(DISTINCT TrackId) FROM InvoiceLine) / (SELECT COUNT(*) FROM Track)")
q("topn", "hard", "Which 5 albums generated the most revenue (UnitPrice times Quantity)? Return album title and revenue, highest first.",
  "SELECT Album.Title, SUM(InvoiceLine.UnitPrice * InvoiceLine.Quantity) AS r FROM InvoiceLine JOIN Track ON Track.TrackId = InvoiceLine.TrackId JOIN Album ON Album.AlbumId = Track.AlbumId GROUP BY Album.AlbumId, Album.Title ORDER BY r DESC LIMIT 5", True, 1)
q("window", "hard", "For each year, which billing country had the highest invoice revenue? Return year and country. Assume no ties.",
  "WITH y AS (SELECT strftime('%Y', InvoiceDate) AS yr, BillingCountry AS c, SUM(Total) AS s FROM Invoice GROUP BY yr, c), r AS (SELECT yr, c, ROW_NUMBER() OVER (PARTITION BY yr ORDER BY s DESC) AS rn FROM y) SELECT yr, c FROM r WHERE rn = 1")
