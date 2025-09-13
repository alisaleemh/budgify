package main

import (
	"database/sql"
	"encoding/json"
	"log"
	"net/http"
	"os"

	_ "github.com/mattn/go-sqlite3"
)

// OpenDB opens a SQLite database located at path.
func OpenDB(path string) (*sql.DB, error) {
	db, err := sql.Open("sqlite3", path)
	if err != nil {
		return nil, err
	}
	return db, nil
}

// GetSpendByCategoryMonth returns monthly spend aggregated by category.
func GetSpendByCategoryMonth(db *sql.DB) ([]map[string]interface{}, error) {
	rows, err := db.Query(`
        SELECT strftime('%Y-%m', date) AS month,
               category,
               ROUND(SUM(amount), 2) AS total_spent
        FROM transactions
        GROUP BY month, category
        ORDER BY month, category;
    `)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var results []map[string]interface{}
	for rows.Next() {
		var month, category string
		var total float64
		if err := rows.Scan(&month, &category, &total); err != nil {
			return nil, err
		}
		results = append(results, map[string]interface{}{
			"month":       month,
			"category":    category,
			"total_spent": total,
		})
	}
	return results, nil
}

// Server wraps the database and exposes HTTP handlers.
type Server struct {
	db *sql.DB
}

// NewServer creates a new Server.
func NewServer(db *sql.DB) *Server {
	return &Server{db: db}
}

// handleGetSpendByCategoryMonth writes the aggregated spend as JSON.
func (s *Server) handleGetSpendByCategoryMonth(w http.ResponseWriter, r *http.Request) {
	data, err := GetSpendByCategoryMonth(s.db)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(data); err != nil {
		log.Printf("encode response: %v", err)
	}
}

// routes registers HTTP routes.
func (s *Server) routes() {
	http.HandleFunc("/get_spend_by_category_month", s.handleGetSpendByCategoryMonth)
}

func main() {
	dbPath := os.Getenv("BUDGIFY_DB")
	if dbPath == "" {
		dbPath = "budget.db"
	}

	db, err := OpenDB(dbPath)
	if err != nil {
		log.Fatalf("failed to open db: %v", err)
	}
	defer db.Close()

	server := NewServer(db)
	server.routes()

	log.Println("MCP server listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
}
