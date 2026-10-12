"""Synthetic tickets, help articles and questions for the fictitious Vértice ERP (plan 0005).

``generate(seed, count)`` builds the dataset; the command line is in ``cli.py``. Nothing here is
real data (rule 9): names, companies and personal data are made up, and the personal data is
recorded in an answer key to measure the anonymization.
"""

from synthetic_tickets.generate import Dataset, generate, write

__all__ = ["Dataset", "generate", "write"]
