"""
``?print_all=1`` — every row on one page, for the print button in the page
header. Browser printing a paginated list used to print only the page on
screen (25 of 448 students) with nothing on the paper saying so.
"""

#: Hard cap so a print of a huge table cannot tie up a worker.
PRINT_ALL_LIMIT = 3000


def page_size(request, default):
    """Rows per page for ``request``: ``default``, or everything for a print."""
    return PRINT_ALL_LIMIT if request.GET.get('print_all') == '1' else default
