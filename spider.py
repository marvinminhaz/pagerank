# Web crawler that stores visited pages and links in a SQLite database,
# then crawls linked pages within the same domain boundary.

import sqlite3
import ssl
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

from bs4 import BeautifulSoup

# Disable SSL certificate verification to avoid HTTPS errors on some sites
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


with sqlite3.connect("spider.sqlite") as conn:
    cur = conn.cursor()

    # Set up three tables:
    # - Pages: tracks URLs, their HTML content, crawl errors, and PageRank values
    # - Links: tracks directed links between pages (from_id -> to_id)
    # - Webs: stores the root domain(s) to stay within during crawling
    cur.executescript("""
    create table if not exists Pages (
        id         integer primary key autoincrement,
        url        text unique,
        html       text,
        error      integer,
        old_rank   real,
        new_rank   real
    );

    create table if not exists Links (
        from_id    integer,
        to_id      integer,
        unique (from_id, to_id)
    );

    create table if not exists Webs (
       url         text unique
    )
    """)

    # Check if there's an unvisited page already in the database (resuming a previous crawl)
    cur.execute("""
    select id, url from Pages
    where html is null and error is null
    order by random() limit 1
    """)

    if cur.fetchone() is not None:
        # Unvisited pages exist — resume where we left off
        print("Restarting crawl. Remove spider.sqlite to start a new crawl.")
    else:
        # No pages yet — start fresh by asking the user for a seed URL
        pageurl = input("Enter a webpage to crawl: ")
        if len(pageurl) < 1:
            pageurl = "https://www.dr-chuck.com/"
        if not pageurl.startswith("http"):
            pageurl = "https://" + pageurl

        weburl = pageurl  # weburl will become the domain boundary for crawling

        # Normalize pageurl: strip trailing slash so URLs are stored consistently
        if pageurl.endswith("/"):
            pageurl = pageurl.rstrip("/")

        # Normalize weburl: if it points to an HTML file, strip the filename
        # so the boundary is set to the containing directory instead
        if weburl.endswith(".htm") or weburl.endswith(".html"):
            weburl = weburl[: weburl.rfind("/")]

        # Seed the Pages table with the starting URL (html=null means unvisited)
        cur.execute(
            "insert into Pages (url, html, new_rank) values (?, null, 1.0)", (pageurl,)
        )
        # Save the root domain to Webs — only URLs starting with this will be crawled
        cur.execute("insert or ignore into Webs (url) values (?)", (weburl,))

    # Load all known root domains into memory for fast boundary checks during crawling
    cur.execute("select url from Webs")
    webs = list()
    for row in cur:
        webs.append(row[0])
    print(webs)

    # --- Main crawl loop ---
    many = 0  # tracks how many pages are left to crawl in the current batch
    while True:
        if many < 1:
            # Ask the user how many pages to crawl before pausing again
            sval = input("Enter number of pages to crawl: ")
            if sval == "":
                break
            if len(sval) < 1:
                print("Invalid input, enter a number of pages to crawl.")
                continue
            if not sval.isdigit():
                print("Invalid input, enter a number of pages to crawl.")
                continue
            if int(sval) < 1:
                print("Invalid input, enter a number of pages to crawl.")
                continue
            many = int(sval)
        many -= 1
        print(f"Crawling page... ({many} remaining)")

        # Pick a random unvisited page from the database
        cur.execute("""
        select id, url from Pages
        where html is null and error is null
        order by random() limit 1
        """)
        row = cur.fetchone()
        if row is None:
            # All discovered pages have been visited — nothing left to crawl
            print("No more pages to crawl.")
            conn.commit()
            break

        from_id = row[0]  # ID of the page being crawled (used to record outgoing links)
        url = row[1]
        print(from_id, url)

        # --- Fetch the page ---
        try:
            with urlopen(url, context=ctx) as response:
                html = response.read()
                status_code = response.getcode()
                content_type = response.info().get_content_type()

                # Skip pages that returned a non-200 status and log the error
                if status_code != 200:
                    print("Error fetching", url, status_code)
                    cur.execute(
                        "update Pages set error = ? where url = ?", (status_code, url)
                    )
                    continue

                # Skip non-HTML resources (PDFs, images, etc.) — remove from Pages entirely
                if content_type is not None and not content_type.startswith(
                    "text/html"
                ):
                    print("Ignoring non text/html page")
                    cur.execute("delete from Pages where url = ?", (url,))
                    continue

                print(f"read {len(html)} characters")

                # Parse the HTML so we can extract links
                soup = BeautifulSoup(html, "html.parser")

        except KeyboardInterrupt:
            # Allow the user to stop crawling cleanly without losing progress
            print("Process interrupted by user")
            conn.commit()
            break
        except Exception as e:
            # Mark page as errored (-1) so it isn't retried
            print(f"Error fetching {url} due to {e}")
            cur.execute("update Pages set error = -1 where url = ?", (url,))
            continue

        # Store the fetched HTML in the database (as a binary memoryview to handle encoding safely)
        cur.execute(
            "insert or ignore into Pages (url, html, new_rank) values (?, null, 1.0)",
            (url,),
        )
        cur.execute("update Pages set html = ? where url = ?", (memoryview(html), url))

        # --- Extract and process all anchor links from the page ---
        tags = soup("a")
        count = 0
        for tag in tags:
            href = tag.get("href", None)
            if href is None:
                continue  # Skip anchors with no href attribute

            if isinstance(href, str):
                # Skip direct links to image files
                if (
                    href.endswith(".png")
                    or href.endswith(".jpg")
                    or href.endswith(".gif")
                ):
                    continue

                # Convert relative URLs (e.g. "../about") to absolute URLs
                up = urlparse(href)
                if len(up.scheme) < 1:
                    href = urljoin(url, href)

                # Strip URL fragment (e.g. "#section2") — fragments point to the same page
                ipos = href.find("#")
                if ipos > 1:
                    href = href[:ipos]

                href = href.strip()
                if not href.startswith("http"):
                    continue  # Discard any remaining non-HTTP URLs (e.g. mailto:)

                # Domain boundary check — only follow links within our known root domains
                found = False
                for web in webs:
                    if href.startswith(web):
                        found = True
                        break
                if not found:
                    continue

                # Add the discovered URL to Pages if it hasn't been seen before
                cur.execute(
                    "insert or ignore into Pages (url, html, new_rank) values (?, null, 1.0)",
                    (href,),
                )
                count += 1

                # Record the directed link: current page -> discovered page
                cur.execute("select id from Pages where url = ?", (href,))
                to_id = cur.fetchone()[0]
                cur.execute(
                    "insert or ignore into Links (from_id, to_id) values (?, ?)",
                    (from_id, to_id),
                )

        print(f"retrieved {count} links")
        conn.commit()  # Persist all changes for this page before moving to the nextk
