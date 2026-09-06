"""The product of level one: HTML and crops, plus a reversible one-at-a-time
swap.

Here and only here is HTML born. Four files, four different jobs:

    crop.py   cut an artifact out of the page by the model's box
    html.py   fold the pages into HTML: text as markup, artifacts as pictures
    swap.py   PURE strings: replace ONE picture with markup -- and undo it
    apply.py  the same over files: the book, the swap journal, the undo stack

The anchor between the levels is the block `id`, and it is PER PAGE:
`p0042-b17`. Not plain `b17`: `block_id` restarts on every page, so a
five-hundred-page book would carry five hundred elements with the same `id`.
Cheap now, dear once the HTML exists.
"""
