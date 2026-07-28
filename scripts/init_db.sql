-- OSINT-Hub PostgreSQL 16 Schema Initialization
-- Sovereign & Zero-Trust Investigation Data Storage

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Table: investigations / scans
CREATE TABLE IF NOT EXISTS scans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    target VARCHAR(255) NOT NULL,
    target_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    ai_summary TEXT
);

-- Table: raw module scan results (Purged automatically after 7 days)
CREATE TABLE IF NOT EXISTS scan_module_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_id UUID NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    module_name VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    execution_time_ms INTEGER DEFAULT 0,
    raw_data JSONB DEFAULT '{}'::jsonb,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table: graph nodes
CREATE TABLE IF NOT EXISTS graph_nodes (
    id VARCHAR(255) PRIMARY KEY,
    scan_id UUID NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    label VARCHAR(255) NOT NULL,
    node_type VARCHAR(50) NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table: graph edges
CREATE TABLE IF NOT EXISTS graph_edges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_id UUID NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    source_node_id VARCHAR(255) NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
    target_node_id VARCHAR(255) NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
    relation VARCHAR(100) NOT NULL,
    confidence FLOAT DEFAULT 1.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast graph queries and 7-day purge efficiency
CREATE INDEX IF NOT EXISTS idx_scans_created_at ON scans(created_at);
CREATE INDEX IF NOT EXISTS idx_scan_module_results_scan_id ON scan_module_results(scan_id);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_scan_id ON graph_nodes(scan_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_scan_id ON graph_edges(scan_id);
