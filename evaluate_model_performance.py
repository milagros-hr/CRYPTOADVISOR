"""
evaluate_model_performance.py
Script de evaluación y backtesting independiente de CryptoAdvisor.
Mide la precisión, recall, F1 por clase y calcula la curva de calibración de probabilidades.
"""

import json
import os
import sys
from collections import Counter

# Asegurar que el directorio del proyecto esté en el path
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.append(PROJECT_DIR)

from models import bayesian_model

DATA_PATH = os.path.join(PROJECT_DIR, "data", "training_data.json")
MODEL_PATH = os.path.join(PROJECT_DIR, "data", "bayesian_network_model.json")

def load_data():
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"No se encontró el dataset en {DATA_PATH}. Debes reentrenar el modelo primero.")
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f).get("samples", [])

def load_model():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"No se encontró el modelo en {MODEL_PATH}. Ejecuta el reentrenamiento.")
    with open(MODEL_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    print("=" * 60)
    print("      CryptoAdvisor - Evaluador de Rendimiento y Calibración")
    print("=" * 60)
    
    try:
        muestras = load_data()
        modelo = load_model()
    except Exception as e:
        print(f"Error: {e}")
        return
        
    print(f"Muestras totales de evaluación: {len(muestras)}")
    print(f"Variables de evidencia usadas: {len(modelo.get('features', []))}")
    print("-" * 60)
    
    correctos = 0
    confusion = {c: {o: 0 for o in ["BUY", "SELL", "HOLD"]} for c in ["BUY", "SELL", "HOLD"]}
    
    # Bins de calibración
    bins = [
        {"min": 0.0, "max": 0.6, "label": " < 60%  ", "correct": 0, "total": 0, "conf_sum": 0.0},
        {"min": 0.6, "max": 0.7, "label": "60%-70% ", "correct": 0, "total": 0, "conf_sum": 0.0},
        {"min": 0.7, "max": 0.8, "label": "70%-80% ", "correct": 0, "total": 0, "conf_sum": 0.0},
        {"min": 0.8, "max": 0.9, "label": "80%-90% ", "correct": 0, "total": 0, "conf_sum": 0.0},
        {"min": 0.9, "max": 1.0, "label": "90%-100%", "correct": 0, "total": 0, "conf_sum": 0.0},
    ]
    
    for m in muestras:
        real = m["recomendacion"]
        evidencia = bayesian_model._muestra_a_evidencia(m)
        probs, _ = bayesian_model.inferir_probabilidades(evidencia, m.get("par"), modelo)
        pred = max(probs, key=probs.get)
        confianza = probs[pred]
        
        confusion[real][pred] += 1
        is_correct = (pred == real)
        if is_correct:
            correctos += 1
            
        # Asignar a bin de calibración
        for b in bins:
            if b["min"] <= confianza < b["max"] or (b["max"] == 1.0 and confianza == 1.0):
                b["total"] += 1
                b["conf_sum"] += confianza
                if is_correct:
                    b["correct"] += 1
                break
                
    accuracy = correctos / len(muestras) if muestras else 0.0
    
    # Calcular baseline
    labels = [m["recomendacion"] for m in muestras]
    counts = Counter(labels)
    majority_class, majority_count = counts.most_common(1)[0]
    baseline = majority_count / len(muestras) if muestras else 0.0
    
    print(f"Accuracy del Modelo:  {accuracy*100:.2f}%")
    print(f"Baseline Mayoritario: {baseline*100:.2f}% ({majority_class})")
    print("-" * 60)
    
    # Métricas detalladas por clase
    print("MÉTRICAS POR CLASE:")
    print(f"{'Clase':<8} | {'Precisión':<10} | {'Recall':<10} | {'F1-Score':<10} | {'Muestras':<8}")
    print("-" * 60)
    
    clases = ["BUY", "SELL", "HOLD"]
    f1_sum = 0.0
    for clase in clases:
        tp = confusion[clase][clase]
        fp = sum(confusion[other][clase] for other in clases if other != clase)
        fn = sum(confusion[clase][other] for other in clases if other != clase)
        
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        f1_sum += f1
        
        print(f"{clase:<8} | {prec*100:9.2f}% | {rec*100:9.2f}% | {f1:9.4f}  | {counts[clase]:<8}")
        
    f1_macro = f1_sum / 3
    print("-" * 60)
    print(f"F1 Macro Promedio: {f1_macro:.4f}")
    print("-" * 60)
    
    # Matriz de Confusión
    print("MATRIZ DE CONFUSIÓN:")
    print(f"{'Real \\ Pred':<12} | {'BUY':<6} | {'SELL':<6} | {'HOLD':<6}")
    print("-" * 60)
    for c in clases:
        print(f"{c:<12} | {confusion[c]['BUY']:<6} | {confusion[c]['SELL']:<6} | {confusion[c]['HOLD']:<6}")
    print("-" * 60)
    
    # Tabla de Calibración
    print("CURVA DE CALIBRACIÓN DE PROBABILIDADES:")
    print(f"{'Intervalo Conf':<14} | {'Nº Casos':<8} | {'Conf. Promedio':<15} | {'Precisión Real':<15}")
    print("-" * 60)
    for b in bins:
        if b["total"] > 0:
            avg_conf = b["conf_sum"] / b["total"]
            real_acc = b["correct"] / b["total"]
            print(f"{b['label']:<14} | {b['total']:<8} | {avg_conf*100:13.2f}% | {real_acc*100:13.2f}%")
        else:
            print(f"{b['label']:<14} | 0        | {'—':<15} | {'—':<15}")
    print("=" * 60)
    print("Interpretación de Calibración:")
    print("  Si la 'Precisión Real' es cercana a la 'Confianza Promedio', el modelo")
    print("  está estadísticamente bien calibrado y sus probabilidades son confiables.")
    print("=" * 60)

if __name__ == "__main__":
    main()
