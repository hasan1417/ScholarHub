-- Enable the pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create a function to create vector indexes (will be called after tables are created)
CREATE OR REPLACE FUNCTION create_vector_indexes()
RETURNS void AS $$
BEGIN
    -- Create vector index for document chunks embeddings
    -- Using HNSW index for fast approximate nearest neighbor search
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_name = 'document_chunks'
    ) THEN
        -- Drop existing index if it exists
        DROP INDEX IF EXISTS idx_document_chunks_embedding;
        
        -- Create HNSW index for fast similarity search
        CREATE INDEX idx_document_chunks_embedding 
        ON document_chunks 
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
        
        -- Create additional indexes for performance
        CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id 
        ON document_chunks(document_id);
        
        CREATE INDEX IF NOT EXISTS idx_document_chunks_chunk_index 
        ON document_chunks(document_id, chunk_index);
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Log that pgvector is enabled
DO $$
BEGIN
    RAISE NOTICE 'pgvector extension enabled successfully';
    RAISE NOTICE 'Vector indexes will be created after tables are available';
END $$;
