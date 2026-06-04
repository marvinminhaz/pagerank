import sqlite3

with sqlite3.connect("spider.sqlite") as conn:
    cur = conn.cursor()

    cur.execute("select distinct from_id from Links")
    from_ids = []
    for row in cur:
        from_ids.append(row[0])

    # Finding ids that recieve page rank
    to_ids = []
    links = []
    cur.execute("select distinct from_id, to_id from Links")

    # Isolating the strongly connected component
    for row in cur:
        from_id = row[0]
        to_id = row[1]
        # excluding pages linking to themselves
        if from_id == to_id:
            continue
        # excluding pages not in from_ids
        if from_id not in from_ids:
            continue
        # excluding pages that are deadends
        if to_id not in from_ids:
            continue
        # adding distinct from_id and to_id into links
        links.append(row)
        # adding all to_id in to_ids
        if to_id not in to_ids:
            to_ids.append(to_id)

    # Initializing ranks in memory
    prev_ranks = {}

    # Iterating over from_ids
    for node in from_ids:
        # retrieving assigned ranks of each node
        cur.execute("select new_rank from Pages where id = ?", (node,))
        row = cur.fetchone()
        # saving each node along with its assigned rank
        prev_ranks[node] = row[0]

    # seeking user input for number of iterations
    many = 1  # default value
    sval = input("Enter number of iterations: ")
    if len(sval) > 1:
        many = int(sval)

    # sanity check
    if not prev_ranks:
        print("Nothing to page rank, check data...")
        quit()

    # dispose
    # for i, (key, val) in enumerate(prev_ranks.items()):
    #     if i > 5: break
    #     print(key, val)
    print(links[:5])

    # The iteration loop
    for i in range(many):
        next_ranks = {}
        total = 0.0

        # iterating over every node and rank pair
        for node, old_rank in prev_ranks.items():
            # adding all previous ranks
            total = total + old_rank
            next_ranks[node] = 0.0

            give_ids = []
            # iterating over every from_id and to_id pair in links
            for from_id, to_id in links:
                if from_id not in to_ids:
                    continue
                if to_id not in to_ids:
                    continue
                give_ids.append(to_id)
                if not give_ids:
                    continue
                amount = old_rank / (len(give_ids))

                for id in give_ids:
                    next_ranks[id] = next_ranks[id] + amount
