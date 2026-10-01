"""Offline research evaluation for LectureMind (not part of the API or worker).

It reuses the production retrieval and grounded-answer code (app.services.rag) against
a frozen, versioned evaluation dataset of lectures processed in a dedicated evaluation
account, and writes results to files, never to production tables such as chat_logs.

Nothing here produces research results by itself: numbers exist only after a real,
frozen dataset (human-written questions with gold spans, human reference transcripts,
human labels) has been run. Example files are marked as examples and the tooling
labels anything computed from them as such.
"""
