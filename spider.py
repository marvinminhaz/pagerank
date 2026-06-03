import urllib.request
import urllib.parse
import urllib.error
import ssl
import sqlite3
from bs4 import BeautifulSoup


# SSL certificate fix
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


# Creating, accessing database
with sqlite3.connect('spider.sqlite') as conn:
    cur = conn.cursor()

    cur.executescript('''
    drop table if exists Pages;
    drop table if exists Links;
    drop table if exists Webs;

    create table Pages (
        id         integer primary key autoincrement,
        url        text unique,
        html       text,
        error      integer,
        old_rank   real,
        new_rank   real
    );

    create table Links (
        from_id    integer,
        to_id      integer
    );

    create table Webs (
       url         text unique
    )
    ''')


    cur.execute('''
    select id, url from Pages 
    where html is null and error is null
    order by random() limit 1
    ''')


    #Starting or resuming
    if cur.fetchone() is not None:
        print('Restarting crawl...')
    else:
        pageurl = input('Enter a webpage to crawl: ')
        if len(pageurl) < 1:
            pageurl = 'https://www.dr-chuck.com/'

    # Initiating weburl if the conditions below do not occur
    weburl = pageurl

    # Processing startingurl to save into Pages
    if pageurl.endswith('/'):
        pageurl = pageurl.rstrip('/')
    # Processing startingurl/web to save into Webs
    if (weburl.endswith('.htm') or weburl.endswith('.html')):
        weburl = weburl[:weburl.rfind('/')]

    # Saving processed pageurl into Pages
    cur.execute('insert into Pages (url, html, new_rank) values (?, null, 1.0)', (pageurl,))
    # Saving processed weburl into Webs
    cur.execute('insert or ignore into Webs (url) values (?)', (weburl,))

    # Webs list for boundary setting
    cur.execute('select url from Webs')
    webs = list()
    for row in cur:
        webs.append(row[0])
    print(webs)


    # Crawl loop
    many = 0
    while True:
        if many < 1:
            sval = input("Enter number of pages to crawl: ")
            if len(sval) < 1:
                break
            many = int(sval)
        many = many - 1
        
        # Picking a random unvisited site
        cur.execute('''
        select id, url from Pages
        where html is null and error is null
        order by random() limit 1 
        ''')
        # selecting id and url of the selected site
        row = cur.fetchone()
        from_id = row[0]
        url = row[1]
        print(from_id, url)


        # Fetching html 
        html = urllib.request.urlopen(url, context=ctx).read()

        #Saving html into Pages
        cur.execute('insert or ignore into Pages (url, html, new_rank) values (?, null, 1.0)', (url,)) 
        cur.execute('update Pages set html = ? where url = ?', (memoryview(html), url)) 

        # Parsing html
        soup = BeautifulSoup(html, 'html.parser')

        tags = soup('a')
        
        count = 0
        for tag in tags:
            href = tag.get('href', None)
            if href is None:
                continue
            # Filtering out images
            if href.endswith('.png') or href.endswith('.jpg') or href.endswith('.gif') or href.endswith('.pdf'):
                continue
            # Resolving relative urls
            up = urllib.parse.urlparse(href)
            if len(up.scheme) < 1:
                href = urllib.parse.urljoin(url, href)
            #handling hrefs with sectional url fragments
            ipos = href.find('#')
            if ipos > 1:
                href = href[:ipos]
            

            # Domain boundary check
            found = False
            for web in webs:
                if href.startswith(web):
                    found = True
                    break
            if not found: 
                continue
            
            # Adding new Pages 
            cur.execute('insert or ignore into Pages (url, html, new_rank) values (?, null, 1.0)', (href, ))
            count += 1

            # Retrieving id and saving it to Links.to_id
            cur.execute('select id from Pages where url = ?', (href, ))
            to_id = cur.fetchone()[0]
            cur.execute('insert or ignore into Links (from_id, to_id) values (?, ?)', (from_id, to_id))

        print(count)
            




    

