(ns test-app.diagnostics-sample)

(defn broken-factory []
  missing-greeting)

(defn broken-consumer []
  (let [value (broken-factory)]
    (println value)
    missing-consumer-value))
