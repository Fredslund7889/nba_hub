<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface Game {
  id: number
  game_date: string
  home_score: number
  away_score: number
  status: string
  home_team: string
  home_team_abbrev: string
  away_team: string
  away_team_abbrev: string
}

interface Player {
  id: number
  first_name: string
  last_name: string
  position: string
  jersey_number: string | null
  photo_url: string
}

interface GameRosters {
  game_id: number
  home_team_players: Player[]
  away_team_players: Player[]
}

const games = ref<Game[]>([])
const error = ref<string | null>(null)
const selectedGame = ref<Game | null>(null)
const rosters = ref<GameRosters | null>(null)
const loadingRosters = ref(false)

const formatDate = (dateString: string) => {
  if (!dateString) return ''
  return dateString.split('T')[0]
}

const fetchRostersForGame = async (game: Game) => {
  selectedGame.value = game
  loadingRosters.value = true
  error.value = null
  rosters.value = null
  
  try {
    const response = await fetch(`http://localhost:8000/games/${game.id}/rosters`)
    if (!response.ok) throw new Error('Kunne ikke hente trupper for denne kamp')
    const data = await response.json()
    rosters.value = data
  } catch (err: any) {
    error.value = err.message
  } finally {
    loadingRosters.value = false
  }
}

onMounted(async () => {
  try {
    const response = await fetch('http://localhost:8000/games')
    if (!response.ok) throw new Error('Kunne ikke hente kampe fra serveren')
    const data = await response.json()
    games.value = data.games || data 
  } catch (err: any) {
    error.value = err.message
  }
})
</script>

<template>
  <main class="container">
    <h1>🏀 NBA Pick 'em Hub</h1>
    <p class="subtitle">Vælg en kamp for at se holdkort og trupper</p>

    <div v-if="error" class="error">
      Fejl: {{ error }}
    </div>

    <div class="layout">
      <!-- Venstre side: Liste over kampe -->
      <div class="games-section">
        <h2>Kampe</h2>
        <div v-if="games.length > 0" class="games-list">
          <div 
            v-for="game in games" 
            :key="game.id" 
            class="game-card"
            @click="fetchRostersForGame(game)"
          >
            <span class="game-date">{{ formatDate(game.game_date) }}</span>
            <div class="matchup">
              <span>{{ game.home_team_abbrev }} vs {{ game.away_team_abbrev }}</span>
            </div>
            <button class="select-btn">Se trup</button>
          </div>
        </div>
        <p v-else>Henter kampe...</p>
      </div>

      <!-- Højre side: Viste trupper for valgt kamp -->
      <div class="roster-section">
        <h2>Holdkort / Trupper</h2>
        
        <div v-if="loadingRosters">Henter trupper...</div>
        
        <div v-else-if="rosters && selectedGame" class="rosters-container">
          <!-- Hjemmehold -->
          <div class="team-roster-box">
            <h3>{{ selectedGame.home_team }} ({{ selectedGame.home_team_abbrev }}) - Hjemmehold</h3>
            <ul class="player-list" v-if="rosters.home_team_players?.length > 0">
              <li v-for="player in rosters.home_team_players" :key="player.id">
                <span class="jersey" v-if="player.jersey_number">#{{ player.jersey_number }}</span>
                <span class="name">{{ player.first_name }} {{ player.last_name }}</span>
                <span class="pos" v-if="player.position">({{ player.position }})</span>
              </li>
            </ul>
            <p v-else class="placeholder-text">Ingen spillere fundet.</p>
          </div>

          <!-- Udehold -->
          <div class="team-roster-box">
            <h3>{{ selectedGame.away_team }} ({{ selectedGame.away_team_abbrev }}) - Udehold</h3>
            <ul class="player-list" v-if="rosters.away_team_players?.length > 0">
              <li v-for="player in rosters.away_team_players" :key="player.id">
                <span class="jersey" v-if="player.jersey_number">#{{ player.jersey_number }}</span>
                <span class="name">{{ player.first_name }} {{ player.last_name }}</span>
                <span class="pos" v-if="player.position">({{ player.position }})</span>
              </li>
            </ul>
            <p v-else class="placeholder-text">Ingen spillere fundet.</p>
          </div>
        </div>

        <p v-else class="placeholder-text">Klik på "Se trup" på en af kampene til venstre for at se spillerne.</p>
      </div>
    </div>
  </main>
</template>

<style scoped>
.container {
  max-width: 1100px;
  margin: 40px auto;
  padding: 24px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
}
h1 { margin-bottom: 4px; color: #1a1a1a; }
.subtitle { color: #666; margin-bottom: 24px; }
.error { color: #d93838; background: #fdf2f2; padding: 12px; border-radius: 6px; margin-bottom: 16px; }

.layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

@media (max-width: 768px) {
  .layout { grid-template-columns: 1fr; }
}

.games-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 600px;
  overflow-y: auto;
}

.game-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.1s ease;
}

.game-card:hover {
  border-color: #0066cc;
  background: #f1f7ff;
}

.game-date { font-size: 0.85rem; color: #555; }
.matchup { font-weight: 600; color: #333; }

.select-btn {
  background: #0066cc;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
}
.select-btn:hover { background: #0051a2; }

.roster-section {
  background: #fdfdfe;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  padding: 16px;
  max-height: 650px;
  overflow-y: auto;
}

.team-roster-box {
  margin-bottom: 20px;
}

.team-roster-box h3 {
  font-size: 1rem;
  color: #333;
  border-bottom: 2px solid #e9ecef;
  padding-bottom: 6px;
  margin-bottom: 8px;
}

.player-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.player-list li {
  padding: 4px 0;
  font-size: 0.9rem;
  border-bottom: 1px solid #f5f5f5;
  display: flex;
  gap: 8px;
}

.jersey {
  font-weight: bold;
  color: #0066cc;
  min-width: 30px;
}

.pos {
  color: #666;
}

.placeholder-text {
  color: #888;
  font-style: italic;
  margin-top: 20px;
}
</style>