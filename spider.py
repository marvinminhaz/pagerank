# Importing necessary libraries
import sqlite3
import ssl
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

from bs4 import BeautifulSoup

# SSL certificate fix
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


# Creating, accessing database
with sqlite3.connect("spider.sqlite") as conn:
    cur = conn.cursor()

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

    cur.execute("""
    select id, url from Pages
    where html is null and error is null
    order by random() limit 1
    """)

    # Starting or resuming
    if cur.fetchone() is not None:
        print("Restarting crawl. Remove spider.sqlite to start a new crawl.")
    else:
        pageurl = input("Enter a webpage to crawl: ")
        if len(pageurl) < 1:
            pageurl = "https://www.dr-chuck.com/"
        if not pageurl.startswith("http"):
            pageurl = "https://" + pageurl

        # Initiating weburl if the conditions below do not occur
        weburl = pageurl

        # Processing startingurl to save into Pages
        if pageurl.endswith("/"):
            pageurl = pageurl.rstrip("/")
        # Processing startingurl/web to save into Webs
        if weburl.endswith(".htm") or weburl.endswith(".html"):
            weburl = weburl[: weburl.rfind("/")]

        # Saving processed pageurl into Pages
        cur.execute(
            "insert into Pages (url, html, new_rank) values (?, null, 1.0)", (pageurl,)
        )
        # Saving processed weburl into Webs
        cur.execute("insert or ignore into Webs (url) values (?)", (weburl,))

    # Webs list for boundary setting
    cur.execute("select url from Webs")
    webs = list()
    for row in cur:
        webs.append(row[0])
    print(webs)

    # Crawl loop
    many = 0
    while True:
        if many < 1:
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
        many = many - 1
        print(f"Crawling page... ({many} remaining)")

        # Picking a random unvisited site
        cur.execute("""
        select id, url from Pages
        where html is null and error is null
        order by random() limit 1
        """)
        # selecting id and url of the selected site
        row = cur.fetchone()
        if row is None:
            print("No more pages to crawl.")
            conn.commit()
            break

        from_id = row[0]
        url = row[1]
        print(from_id, url)

        try:
            with urlopen(url, context=ctx) as response:
                html = response.read()
                status_code = response.getcode()
                content_type = response.info().get_content_type()
                if status_code != 200:
                    print("Error fetching", url, status_code)
                    cur.execute(
                        "update Pages set error = ? where url = ?", (status_code, url)
                    )
                    continue
                if content_type is not None and not content_type.startswith(
                    "text/html"
                ):
                    print("Ignoring non text/html page")
                    cur.execute("delete from Pages where url = ?", (url,))
                    continue
                print(f"read {len(html)} characters")

                # parsing html
                soup = BeautifulSoup(html, "html.parser")

        except KeyboardInterrupt:
            print("Process interrupted by user")
            conn.commit()
            break
        except Exception as e:
            print(f"Error fetching {url} due to {e}")
            cur.execute("update Pages set error = -1 where url = ?", (url,))
            continue

        # Saving html into Pages
        cur.execute(
            "insert or ignore into Pages (url, html, new_rank) values (?, null, 1.0)",
            (url,),
        )
        cur.execute("update Pages set html = ? where url = ?", (memoryview(html), url))

        # Extracting tags
        tags = soup("a")
        count = 0
        for tag in tags:
            href = tag.get("href", None)
            if href is None:
                continue
            if isinstance(href, str):
                # Filtering out images
                if (
                    href.endswith(".png")
                    or href.endswith(".jpg")
                    or href.endswith(".gif")
                ):
                    continue

                # Resolving relative urls
                up = urlparse(href)
                if len(up.scheme) < 1:
                    href = urljoin(url, href)

                # handling hrefs with sectional url fragments
                ipos = href.find("#")
                if ipos > 1:
                    href = href[:ipos]

                # Final resolution of hrefs
                href = href.strip()
                if not href.startswith("http"):
                    continue

                # Domain boundary check
                found = False
                for web in webs:
                    if href.startswith(web):
                        found = True
                        break
                if not found:
                    continue

                # Adding new Pages
                cur.execute(
                    "insert or ignore into Pages (url, html, new_rank) values (?, null, 1.0)",
                    (href,),
                )
                count += 1

                # Retrieving id and saving it to Links.to_id
                cur.execute("select id from Pages where url = ?", (href,))
                to_id = cur.fetchone()[0]
                cur.execute(
                    "insert or ignore into Links (from_id, to_id) values (?, ?)",
                    (from_id, to_id),
                )

        print(f"retrieved {count} links")
        conn.commit()
