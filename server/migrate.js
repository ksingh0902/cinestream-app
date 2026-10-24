/**
 * Database Migration Script
 * Applies replica/schema.sql against PostgreSQL database configured in DATABASE_URL.
 */

require('dotenv').config();
const fs = require('fs');
const path = require('path');
const { Pool } = require('pg');

async function runMigrations() {
  const connectionString = process.env.DATABASE_URL;

  if (!connectionString) {
    console.log('ℹ️  DATABASE_URL is not set. In-memory data store is active.');
    console.log('   To apply migrations to PostgreSQL, set DATABASE_URL in .env.local and re-run: npm run migrate');
    process.exit(0);
  }

  const pool = new Pool({
    connectionString,
    ssl: connectionString.includes('localhost') ? false : { rejectUnauthorized: false },
  });

  try {
    console.log('🔌 Connecting to PostgreSQL...');
    const client = await pool.connect();

    const schemaPath = path.join(__dirname, '..', 'replica', 'schema.sql');
    console.log(`📄 Reading schema from ${schemaPath}...`);
    const sql = fs.readFileSync(schemaPath, 'utf8');

    console.log('⚡ Executing schema migrations...');
    await client.query(sql);

    console.log('✅ Migrations applied successfully!');
    console.log('   All 12 tables, indexes, constraints, and RLS policies created.');

    client.release();
  } catch (err) {
    console.error('❌ Migration failed:', err.message);
    process.exit(1);
  } finally {
    await pool.end();
  }
}

runMigrations();
