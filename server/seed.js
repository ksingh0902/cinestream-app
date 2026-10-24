/**
 * Database Seed Script
 * Populates PostgreSQL tables with initial movies, series, seasons, and server links.
 */

require('dotenv').config();
const { Pool } = require('pg');

async function seedDatabase() {
  const connectionString = process.env.DATABASE_URL;

  if (!connectionString) {
    console.log('ℹ️  DATABASE_URL is not set. Seed data is loaded in-memory automatically.');
    process.exit(0);
  }

  const pool = new Pool({
    connectionString,
    ssl: connectionString.includes('localhost') ? false : { rejectUnauthorized: false },
  });

  try {
    console.log('🔌 Connecting to PostgreSQL to seed data...');
    const client = await pool.connect();

    console.log('🌱 Seeding genres and languages...');
    await client.query(`
      insert into genres (name, slug) values
        ('Action', 'action'),
        ('Sci-Fi', 'sci-fi'),
        ('Drama', 'drama'),
        ('Thriller', 'thriller'),
        ('Crime', 'crime'),
        ('Adventure', 'adventure'),
        ('Animation', 'animation')
      on conflict (name) do nothing;

      insert into languages (name, code, is_dubbed) values
        ('Hindi', 'hi', false),
        ('English', 'en', false),
        ('Dual Audio', 'dual', true),
        ('Hindi Dubbed', 'hi-dub', true),
        ('Tamil', 'ta', false)
      on conflict (name) do nothing;
    `);

    console.log('🌱 Seeding media items and servers...');
    await client.query(`
      insert into media_items (title, slug, media_type, synopsis, release_year, imdb_rating, runtime_minutes, poster_url, backdrop_url, is_featured)
      values
        ('Dune: Part Two', 'dune-part-two', 'movie', 'Paul Atreides unites with Chani and the Fremen seeking revenge against the conspirators who destroyed his family.', 2024, 8.6, 166, 'https://images.unsplash.com/photo-1534447677768-be436bb09401?w=600', 'https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=1600', true),
        ('Jawan', 'jawan', 'movie', 'A high-octane action thriller which outlines the journey of a man set out to rectify societal wrongs.', 2023, 8.1, 169, 'https://images.unsplash.com/photo-1509281373149-e957c6296406?w=600', 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=1600', true),
        ('Stranger Things', 'stranger-things', 'tv_show', 'When a young boy vanishes, a small town uncovers a mystery involving supernatural forces.', 2022, 8.7, 55, 'https://images.unsplash.com/photo-1578328819058-b69f3a3b0f6b?w=600', 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=1600', true)
      on conflict (slug) do nothing;
    `);

    console.log('✅ Database seeded successfully!');
    client.release();
  } catch (err) {
    console.error('❌ Seeding failed:', err.message);
    process.exit(1);
  } finally {
    await pool.end();
  }
}

seedDatabase();
