"""The web: users, their stores, jobs in the background, and HTTP over the
service.

A user owns a store under the data home and reaches nothing else; the admin's
store is the data home. A job is a row in the database and a thread over one
`core/job.py:Job` of its own, whose stop and sink are that job's alone: the
sink turns the log's numbers into progress on the row and into events a
client listens to, and cancel sets the stop the loops already ask. The run
directory stays the durable record of the result; the row is the record of
the job. Nothing here knows a model or a metric: every command goes through
`service`, with the caller's job handed in.
"""
