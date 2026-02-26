# --- ESCENARIO DE PRUEBA ---
@main_bp.route('/debug/escenario_completo')
@login_required
def escenario_completo():
    try:
        # 1. Limpiar BD (Orden inverso a dependencias)
        DetalleVenta.query.delete()
        Venta.query.delete()
        ConsumoInsumo.query.delete()
        LaborCampo.query.delete()
        LoteProduccion.query.delete()
        MovimientoInventario.query.delete()
        LoteInsumo.query.delete()
        DetallePedidoCompra.query.delete()
        PedidoCompra.query.delete()
        Insumo.query.delete()
        Especie.query.delete()
        Cliente.query.delete()
        Proveedor.query.delete()
        Sede.query.delete()
        UnidadMedida.query.delete()
        db.session.flush()

        # 2. Unidades
        kg = UnidadMedida(nombre='Kilogramo', abreviatura='Kg'); db.session.add(kg)
        und = UnidadMedida(nombre='Unidad', abreviatura='Und'); db.session.add(und)
        bto = UnidadMedida(nombre='Bulto', abreviatura='Bto'); db.session.add(bto)
        litro = UnidadMedida(nombre='Litro', abreviatura='L'); db.session.add(litro)
        db.session.flush()

        # 3. Sedes y Terceros
        sede_finca = Sede(nombre='Finca El Paraíso', tipo='Finca', ubicacion_geo='Vereda La Fuente'); db.session.add(sede_finca)
        sede_bodega = Sede(nombre='Bodega Central', tipo='Bodega', ubicacion_geo='Centro'); db.session.add(sede_bodega)
        
        prov_agro = Proveedor(razon_social='AgroInsumos Ltda', nit_rut='900100200', contacto_nombre='Carlos', telefono='3001234567'); db.session.add(prov_agro)
        prov_plasti = Proveedor(razon_social='Plasticos y Materas', nit_rut='800900100', contacto_nombre='Ana', telefono='3109876543'); db.session.add(prov_plasti)

        cli_mostrador = Cliente(nombre='Cliente Mostrador', documento='222222', telefono='000', direccion='Local'); db.session.add(cli_mostrador)
        cli_juan = Cliente(nombre='Juan Pérez', documento='1098765432', telefono='3201112233', direccion='Calle 123'); db.session.add(cli_juan)
        db.session.flush()

        # 4. Insumos y Especies
        # Insumo Consumible
        abono = Insumo(nombre='Triple 15', codigo='INS-001', tipo='Insumo', unidad_medida_id=kg.id, stock_minimo=10, cantidad_actual=0, costo_promedio=0); db.session.add(abono)
        # Insumo Revendible (Mercancia)
        matera = Insumo(nombre='Matera Barro N14', codigo='MAT-14', tipo='Matera', unidad_medida_id=und.id, stock_minimo=5, cantidad_actual=0, costo_promedio=0); db.session.add(matera)
        
        tomate = Especie(nombre_comun='Tomate Chonto', dias_ciclo_estimado=90); db.session.add(tomate)
        db.session.flush()

        # 5. Simular Compras (Entradas FIFO)
        # Compra 1: Abono Barato (Fecha vieja)
        pedido1 = PedidoCompra(numero_orden='OC-AUTO-001', proveedor_id=prov_agro.id, sede_id=sede_bodega.id, fecha_solicitud=datetime(2023,1,10).date(), fecha_recepcion=datetime(2023,1,12).date(), estado='Recibido', total_estimado=200000); db.session.add(pedido1); db.session.flush()
        
        # Lote 1 de Abono: 50 Kg a $4.000
        lote_abono_1 = LoteInsumo(insumo_id=abono.id, pedido_id=pedido1.id, fecha_compra=pedido1.fecha_recepcion, cantidad_inicial=50, cantidad_actual=50, costo_unitario=4000)
        db.session.add(lote_abono_1)
        abono.cantidad_actual += 50
        
        # Compra 2: Abono Caro (Fecha nueva)
        pedido2 = PedidoCompra(numero_orden='OC-AUTO-002', proveedor_id=prov_agro.id, sede_id=sede_bodega.id, fecha_solicitud=datetime(2023,2,1).date(), fecha_recepcion=datetime(2023,2,2).date(), estado='Recibido', total_estimado=250000); db.session.add(pedido2); db.session.flush()
        
        # Lote 2 de Abono: 50 Kg a $5.000
        lote_abono_2 = LoteInsumo(insumo_id=abono.id, pedido_id=pedido2.id, fecha_compra=pedido2.fecha_recepcion, cantidad_inicial=50, cantidad_actual=50, costo_unitario=5000)
        db.session.add(lote_abono_2)
        abono.cantidad_actual += 50

        # Recalcular costo promedio abono
        recalcular_costo_promedio(abono)

        # Compra 3: Materas (Para revender)
        pedido3 = PedidoCompra(numero_orden='OC-AUTO-003', proveedor_id=prov_plasti.id, sede_id=sede_bodega.id, fecha_solicitud=datetime(2023,1,15).date(), fecha_recepcion=datetime(2023,1,15).date(), estado='Recibido', total_estimado=300000); db.session.add(pedido3); db.session.flush()
        
        lote_matera = LoteInsumo(insumo_id=matera.id, pedido_id=pedido3.id, fecha_compra=pedido3.fecha_recepcion, cantidad_inicial=100, cantidad_actual=100, costo_unitario=3000)
        db.session.add(lote_matera)
        matera.cantidad_actual += 100
        recalcular_costo_promedio(matera)

        # 6. Simular Producción (Consumo de Insumos)
        lote_cultivo = LoteProduccion(codigo_lote='L-TOM-001', especie_id=tomate.id, sede_id=sede_finca.id, cantidad_sembrada=1000, cantidad_actual=1000, fecha_siembra=datetime(2023,1,20).date(), ubicacion='Bloque A', estado='En Crecimiento'); db.session.add(lote_cultivo); db.session.flush()
        
        # Labor: Fertilización (Gastamos 60kg de Abono)
        labor = LaborCampo(lote_id=lote_cultivo.id, tipo_labor='Fertilización Inicial', descripcion='Aplicación Triple 15', usuario_id=current_user.id, fecha=datetime.utcnow().date()); db.session.add(labor); db.session.flush()
        
        costo_consumo, _ = consumir_stock_fifo(abono, 60)
        
        consumo = ConsumoInsumo(labor_id=labor.id, insumo_id=abono.id, cantidad=60, subtotal=costo_consumo)
        db.session.add(consumo)
        
        lote_cultivo.costo_total += costo_consumo
        
        mov_consumo = MovimientoInventario(tipo_movimiento='Consumo Interno', cantidad=60, costo_unitario=costo_consumo/60, referencia=f'Labor {lote_cultivo.codigo_lote}', insumo_id=abono.id)
        db.session.add(mov_consumo)

        db.session.commit()
        
        flash('Escenario Completo Generado: Inventario, Compras FIFO y Cultivos activos.', 'success')
        return redirect(url_for('main.dashboard'))

    except Exception as e:
        db.session.rollback()
        return f"Error generando escenario: {str(e)}"