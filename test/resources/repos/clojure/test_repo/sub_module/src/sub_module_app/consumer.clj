(ns sub-module-app.consumer
  "A consumer of test-app.core that lives in a sibling module with its own deps.edn,
  mimicking the multi-module layout of real-world Clojure projects (e.g. penpot's
  common/, frontend/, backend/ split). The bug being reproduced: references to
  symbols defined in test-app.core are missed for files in sibling modules until
  those files are explicitly opened/indexed via find_symbol or get_symbols_overview."
  (:require [test-app.core :as core]))

(defn quadruple-product
  [a b]
  (core/multiply 4 (core/multiply a b)))

(defn quintuple-product
  [a b]
  (core/multiply 5 (core/multiply a b)))
