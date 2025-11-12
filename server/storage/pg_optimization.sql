-- PostgreSQL/pgvector 性能优化配置
-- 优化⑨：pgvector 优化配置

-- 1. 创建 HNSW 索引（如果使用 HNSW）
-- 注意：HNSW 索引需要 pgvector >= 0.5.0
-- CREATE INDEX IF NOT EXISTS transcripts_embedding_hnsw 
-- ON transcripts USING hnsw (embedding vector_cosine_ops)
-- WITH (m = 16, ef_construction = 64);

-- 2. 创建 IVFFlat 索引（备选方案，适用于大规模数据）
-- CREATE INDEX IF NOT EXISTS transcripts_embedding_ivfflat 
-- ON transcripts USING ivfflat (embedding vector_cosine_ops)
-- WITH (lists = 100);

-- 3. 设置维护工作内存（优化索引构建和查询）
-- SET maintenance_work_mem = '512MB';

-- 4. 启用并行计划（优化查询性能）
-- SET enable_parallel_plan = ON;
-- SET max_parallel_workers_per_gather = 4;

-- 5. 如果使用 HNSW 索引，优化搜索参数
-- ALTER INDEX transcripts_embedding_hnsw SET (ef_search = 100);
-- 注意：ef_search 越大，搜索越准确但越慢，建议值：50-200

-- 6. 优化查询计划器统计信息
-- ANALYZE transcripts;
-- ANALYZE knowledge_base;

-- 7. 设置连接池参数（在应用层配置，如 asyncpg）
-- min_size=2, max_size=10

-- 使用说明：
-- 1. 根据数据规模选择合适的索引类型：
--    - 小规模（<100万向量）：IVFFlat
--    - 中大规模（>100万向量）：HNSW
-- 
-- 2. 索引构建时间：
--    - IVFFlat：较快，但查询精度略低
--    - HNSW：较慢，但查询精度高
--
-- 3. 查询性能优化：
--    - ef_search 参数影响查询速度和精度平衡
--    - 并行查询可以显著提升性能
--
-- 4. 定期维护：
--    - 定期运行 ANALYZE 更新统计信息
--    - 监控索引使用情况（pg_stat_user_indexes）

