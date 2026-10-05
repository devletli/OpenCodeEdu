# Chapter 1: EXPLAIN ANALYZE Deep-Dive for Django ORM Queries

Understanding how Django ORM translates to SQL and how PostgreSQL executes those queries is crucial for performance tuning. This chapter dives into using `EXPLAIN ANALYZE` to dissect query plans, identify common Django ORM anti-patterns, and apply effective indexing strategies.

## 1.1 Reading EXPLAIN ANALYZE Output

When you run `EXPLAIN ANALYZE` on a query, PostgreSQL returns a detailed execution plan. Key elements to examine include:

- **Cost**: Planner's estimate of work (in arbitrary units) to execute the plan. Shown as `startup cost..total cost`. Focus on total cost for overall expense.
- **Rows**: Planner's estimate of rows returned by the plan node.
- **Actual Time**: Time (in milliseconds) spent in the plan node, shown as `actual time=startup..total` after `ANALYZE`. Includes time for child nodes.
- **Buffers**: Buffer usage (if `BUFFERS` option used): `shared hit=X, read=Y, dirtied=Z, written=W`. Indicates cache efficiency (hits vs. disk reads).

Example output snippet:
```
->  Seq Scan on django_session  (cost=0.00..35.80 rows=1780 width=26) (actual time=0.012..0.215 rows=1800 loops=1)
      Buffers: shared hit=1800
```

## 1.2 Common Django ORM Anti-Patterns in Query Plans

### N+1 Query Problem
Occurs when Django makes one query to fetch a list of objects, then additional queries for each object to fetch related data.
**In EXPLAIN**: Multiple similar index scans or sequential scans on the same table, each with low row count (often 1), appearing in a loop-like pattern in the plan.

### Missing Indexes
When Django filters or orders on fields without database indexes, PostgreSQL resorts to sequential scans.
**In EXPLAIN**: `Seq Scan` on large tables (high estimated rows) with a `Filter` condition. Look for high `actual time` and `Buffers: shared read=` indicating disk reads.

### Sequential Scans on Large Tables
Even with indexes, poor query construction (e.g., functions on indexed columns) can prevent index usage.
**In EXPLAIN**: `Seq Scan` where an `Index Scan` is expected, especially when `rows` estimate is high (thousands+).

### Cartesian Products (Joins without Conditions)
Accidentally creating cross joins due to missing `select_related` or `prefetch_related`.
**In EXPLAIN**: `Nested Loop` with high row estimates multiplying rapidly, or `Hash Join` with large hash buckets.

## 1.3 Practical Indexing Strategies for Django Relations

### ForeignKey Fields
Django automatically creates an index for `ForeignKey` fields. However, consider:
- **Composite Indexes**: For frequent filters on `ForeignKey` plus another column (e.g., `status` and `created_at`), create a multi-column index.
- **Index Naming**: Django's default index names can be long; use `db_index=True` explicitly and optionally `indexes` in Meta for custom names.

Example:
```python
class Book(models.Model):
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    published = models.DateField()
    class Meta:
        indexes = [
            models.Index(fields=['author', 'published'], name='book_author_pub_idx')
        ]
```

### ManyToMany Fields
Django creates an intermediary table with two foreign keys (both indexed). For performance:
- **Index on the Through Table**: Ensure the intermediary table's foreign keys are indexed (they are by default).
- **Covering Indexes**: If you frequently query the M2M relationship with additional filters on the intermediary table, add indexes on those columns.

Example with a custom through model:
```python
class Membership(models.Model):
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    date_joined = models.DateField()
    class Meta:
        indexes = [
            models.Index(fields=['group', 'date_joined'], name='membership_group_date_idx')
        ]
```

### Index Selection Guidelines
1. **Index ForeignKeys used in filters, joins, or ordering**.
2. **Index fields used in `WHERE`, `ORDER BY`, `GROUP BY`**.
3. **Avoid over-indexing**: Each index slows down writes; prioritize based on query frequency (use `pg_stat_statements`).
4. **Use `EXPLAIN ANALYZE` to verify index usage** after adding indexes.

## 1.4 Tune-Once-Run-Forever Checklist Template

For each anti-pattern identified, apply this checklist to ensure lasting optimization:

### For N+1 Queries
- [ ] Identify the triggering query (usually a `select_related` or `prefetch_related` missing).
- [ ] Add appropriate `select_related` (for single-valued relations) or `prefetch_related` (for multi-valued).
- [ ] Verify with `EXPLAIN ANALYZE` that the number of queries drops to O(1).
- [ ] Check that the plan shows efficient joins (e.g., `Hash Join` or `Merge Join`) instead of repeated scans.
- [ ] Document the fix in a comment near the query or in a project performance wiki.

### For Missing Indexes
- [ ] Identify the table and column(s) causing the sequential scan.
- [ ] Add a database index via Django migration (`AddIndex` or `index_together`).
- [ ] Confirm index usage with `EXPLAIN ANALYZE` showing `Index Scan` or `Bitmap Index Scan`.
- [ ] Monitor index bloat and effectiveness periodically (e.g., quarterly).
- [ ] Add a migration note explaining the performance rationale.

### For Sequential Scans on Large Tables
- [ ] Verify if an appropriate index exists but is not being used (check for operator mismatches or function usage).
- [ ] Rewrite the query to be index-friendly (e.g., avoid `WHERE lower(name) = 'foo'`; instead store lowercase and index that).
- [ ] If no suitable index exists, create one covering the filtered columns.
- [ ] Re-run `EXPLAIN ANALYZE` to confirm index usage and reduced actual time.
- [ ] Set up a pg_stat_statements alert for scans exceeding a threshold (e.g., >100ms).

### General Maintenance
- [ ] Review query plans after major Django or PostgreSQL version upgrades.
- [ ] Schedule monthly `EXPLAIN ANALYZE` on critical queries during low-traffic periods.
- [ ] Update the checklist as new query patterns emerge in the codebase.
- [ ] Share findings with the team via a living document (this handbook!).

By following this chapter's guidance and applying the tune-once-run-forever checklist, you can systematically eliminate performance regressions and maintain optimal Django-PostgreSQL interactions.
