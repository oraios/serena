(ns test-app.extra
  (:require [test-app.core :as core]))

(defn double-product
  "Computes 2 * a * b by calling core/multiply twice."
  [a b]
  (core/multiply 2 (core/multiply a b)))

(defn triple-product
  "Computes a * b * c by calling core/multiply twice."
  [a b c]
  (core/multiply a (core/multiply b c)))
