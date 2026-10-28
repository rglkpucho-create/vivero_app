import pytest
from app.extensions import db
from app.models import Insumo, LoteInsumo
from app.views.helpers import consumir_stock_fifo, recalcular_costo_promedio


def test_consumo_fifo_primer_lote(app, test_data):
    """Verifica que el consumo extrae primero del lote más antiguo."""
    with app.app_context():
        insumo = db.session.get(Insumo, test_data['insumo_id'])
        # Lote 1: 10 u @ 20,000
        # Lote 2: 20 u @ 27,500
        # Total: 30 u
        
        costo_total, costo_unitario = consumir_stock_fifo(insumo, 5.0)
        db.session.commit()
        
        # 5 unidades extraídas de Lote 1 @ 20,000 = 100,000
        assert costo_total == 100000.0
        assert costo_unitario == 20000.0
        assert insumo.cantidad_actual == 25.0
        
        lotes = LoteInsumo.query.filter_by(insumo_id=insumo.id).order_by(LoteInsumo.fecha_compra.asc()).all()
        assert lotes[0].cantidad_actual == 5.0
        assert lotes[1].cantidad_actual == 20.0


def test_consumo_fifo_multilote(app, test_data):
    """Verifica que al agotarse el lote más antiguo, continúa con el siguiente en orden cronológico."""
    with app.app_context():
        insumo = db.session.get(Insumo, test_data['insumo_id'])
        
        # Consumir 15 unidades: agota los 10 de Lote 1 y toma 5 de Lote 2
        # (10 * 20,000) + (5 * 27,500) = 200,000 + 137,500 = 337,500
        costo_total, costo_unitario = consumir_stock_fifo(insumo, 15.0)
        db.session.commit()
        
        assert costo_total == 337500.0
        assert round(costo_unitario, 2) == 22500.0
        assert insumo.cantidad_actual == 15.0
        
        lotes = LoteInsumo.query.filter_by(insumo_id=insumo.id).order_by(LoteInsumo.fecha_compra.asc()).all()
        assert lotes[0].cantidad_actual == 0.0
        assert lotes[1].cantidad_actual == 15.0
        
        # Como solo queda el lote 2 activo, el costo promedio del insumo debe recalcularse a 27,500
        assert insumo.costo_promedio == 27500.0


def test_consumo_fifo_stock_insuficiente(app, test_data):
    """Verifica que se lance excepción si se solicita más del stock disponible."""
    with app.app_context():
        insumo = db.session.get(Insumo, test_data['insumo_id'])
        
        with pytest.raises(Exception) as exc_info:
            consumir_stock_fifo(insumo, 100.0)
            
        assert "Stock insuficiente" in str(exc_info.value)
