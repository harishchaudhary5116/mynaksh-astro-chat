// Run once at startup. Unique keys give us MERGE-based dedup for free.
CREATE CONSTRAINT user_id      IF NOT EXISTS FOR (u:User)       REQUIRE u.user_id IS UNIQUE;
CREATE CONSTRAINT goal_key     IF NOT EXISTS FOR (g:Goal)       REQUIRE g.key     IS UNIQUE;
CREATE CONSTRAINT interest_key IF NOT EXISTS FOR (i:Interest)   REQUIRE i.key     IS UNIQUE;
CREATE CONSTRAINT pref_key     IF NOT EXISTS FOR (p:Preference) REQUIRE p.key     IS UNIQUE;
CREATE CONSTRAINT area_key     IF NOT EXISTS FOR (a:LifeArea)   REQUIRE a.key     IS UNIQUE;
CREATE CONSTRAINT zodiac_name  IF NOT EXISTS FOR (z:ZodiacSign) REQUIRE z.name    IS UNIQUE;
CREATE CONSTRAINT memory_key   IF NOT EXISTS FOR (m:Memory)     REQUIRE m.key     IS UNIQUE;
