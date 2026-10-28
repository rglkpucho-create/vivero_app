import io
from datetime import datetime
from fpdf import FPDF
from fpdf.enums import XPos, YPos


def clean_text(text):
    """Limpia caracteres incompatibles con latin-1 para FPDF2 estándar."""
    if text is None:
        return ""
    text = str(text)
    replacements = {
        '—': '-', '–': '-', '“': '"', '”': '"', '‘': "'", '’': "'",
        '…': '...', '•': '*', '🌱': '', '🚜': '', '🌾': '', '🐄': '',
        '💰': '', '✅': '', '❌': '', '⚠️': '', '📦': '', '🏷️': ''
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode('latin-1', 'replace').decode('latin-1')


class FacturaComercialPDF(FPDF):
    def __init__(self, venta):
        super().__init__(orientation='P', unit='mm', format='letter')
        self.venta = venta
        self.empresa = venta.empresa
        self.cliente = venta.cliente
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(15, 15, 15)

    def header(self):
        # Franja superior decorativa
        self.set_fill_color(5, 150, 105) # Verde EcoSistem Emerald
        self.rect(0, 0, 216, 5, 'F')
        
        # Datos Empresa (Izquierda)
        self.set_xy(15, 12)
        self.set_font('Helvetica', 'B', 16)
        self.set_text_color(30, 41, 59)
        nombre_empresa = self.empresa.nombre if self.empresa else "EcoSistem Agro"
        self.cell(115, 7, clean_text(nombre_empresa), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_font('Helvetica', '', 8)
        self.set_text_color(100, 116, 139)
        nit = f"NIT / RUT: {self.empresa.nit_rut}" if self.empresa and self.empresa.nit_rut else "NIT: Régimen Agropecuario"
        tel = f"Tel: {self.empresa.telefono}" if self.empresa and self.empresa.telefono else ""
        direc = f"Dir: {self.empresa.direccion}" if self.empresa and self.empresa.direccion else ""
        ciudad = f"{self.empresa.ciudad}" if self.empresa and self.empresa.ciudad else "Colombia"
        email = f"Email: {self.empresa.email}" if self.empresa and self.empresa.email else ""
        
        empresa_info = f"{nit} | {tel}\n{direc} - {ciudad}\n{email}"
        self.set_x(15)
        self.multi_cell(115, 4, clean_text(empresa_info))

        # Caja de Factura (Derecha)
        self.set_xy(135, 12)
        self.set_fill_color(248, 250, 252)
        self.set_draw_color(226, 232, 240)
        self.rect(135, 12, 66, 28, 'FD')
        
        self.set_xy(135, 14)
        self.set_font('Helvetica', 'B', 11)
        self.set_text_color(5, 150, 105)
        self.cell(66, 5, "FACTURA DE VENTA", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_x(135)
        self.set_font('Helvetica', 'B', 12)
        self.set_text_color(30, 41, 59)
        num_fac = self.venta.numero_factura or f"POS-{self.venta.id}"
        self.cell(66, 5, f"No. {clean_text(num_fac)}", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_x(135)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(71, 85, 105)
        fecha_str = self.venta.fecha.strftime('%d/%m/%Y %H:%M') if self.venta.fecha else datetime.now().strftime('%d/%m/%Y')
        self.cell(66, 4, f"Fecha: {fecha_str}", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_x(135)
        tipo = self.venta.tipo_venta or "Contado"
        self.cell(66, 4, f"Tipo: {tipo} | Estado: {clean_text(self.venta.estado)}", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(6)

    def footer(self):
        self.set_y(-20)
        self.set_draw_color(226, 232, 240)
        self.line(15, self.get_y(), 201, self.get_y())
        
        self.set_y(-18)
        self.set_font('Helvetica', 'I', 7)
        self.set_text_color(148, 163, 184)
        self.cell(100, 4, "Factura comercial generada por EcoSistem ERP SaaS - www.ecosistem.co", align='L')
        self.cell(86, 4, f"Pagina {self.page_no()}/{{nb}}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_x(15)
        self.cell(186, 4, "Documento equivalente a factura de venta para efectos comerciales y de control interno.", align='C')

    def render_cliente_info(self):
        self.set_draw_color(226, 232, 240)
        self.set_fill_color(248, 250, 252)
        y_start = self.get_y()
        self.rect(15, y_start, 186, 22, 'FD')
        
        self.set_xy(18, y_start + 2)
        self.set_font('Helvetica', 'B', 8)
        self.set_text_color(5, 150, 105)
        self.cell(90, 4, "DATOS DEL CLIENTE / RECEPTOR", new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.cell(90, 4, "INFORMACION DE PAGO Y ATENCION", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_font('Helvetica', '', 8)
        self.set_text_color(51, 65, 85)
        
        # Columna Izquierda
        nombre_cli = self.cliente.nombre if self.cliente else "Cliente General (Consumidor Final)"
        doc_cli = f"Doc/NIT: {self.cliente.documento}" if self.cliente and self.cliente.documento else "Doc: 222222222222"
        tel_cli = f"Tel: {self.cliente.telefono}" if self.cliente and self.cliente.telefono else ""
        dir_cli = f"Dir: {self.cliente.direccion}" if self.cliente and self.cliente.direccion else ""
        
        self.set_xy(18, y_start + 7)
        self.cell(90, 4, clean_text(f"Nombre: {nombre_cli}"))
        self.set_xy(18, y_start + 11)
        self.cell(90, 4, clean_text(f"{doc_cli} | {tel_cli}"))
        self.set_xy(18, y_start + 15)
        self.cell(90, 4, clean_text(f"{dir_cli}"))
        
        # Columna Derecha
        nombre_cajero = self.venta.usuario.nombre_completo if (self.venta.usuario and hasattr(self.venta.usuario, 'nombre_completo')) else "Sistema POS"
        cajero = f"Atendido por: {nombre_cajero}"
        pago = f"Metodo Pago: {self.venta.metodo_pago or 'Efectivo'}"
        vence = f"Vence: {self.venta.fecha_vencimiento.strftime('%d/%m/%Y')}" if self.venta.fecha_vencimiento else "Vence: Inmediato"
        
        self.set_xy(110, y_start + 7)
        self.cell(90, 4, clean_text(cajero))
        self.set_xy(110, y_start + 11)
        self.cell(90, 4, clean_text(pago))
        self.set_xy(110, y_start + 15)
        self.cell(90, 4, clean_text(vence))
        
        self.set_y(y_start + 26)

    def render_items_table(self):
        # Encabezado de la tabla
        self.set_fill_color(30, 41, 59) # Slate oscuro premium
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 8)
        
        col_w = [15, 80, 25, 25, 16, 25]
        # Total: 15 + 80 + 25 + 25 + 16 + 25 = 186 mm
        
        self.cell(col_w[0], 7, "Cant.", border=0, align='C', fill=True)
        self.cell(col_w[1], 7, "Descripcion / Articulo", border=0, align='L', fill=True)
        self.cell(col_w[2], 7, "Tipo", border=0, align='C', fill=True)
        self.cell(col_w[3], 7, "Precio Unit.", border=0, align='R', fill=True)
        self.cell(col_w[4], 7, "Dcto.", border=0, align='C', fill=True)
        self.cell(col_w[5], 7, "Subtotal", border=0, align='R', fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        # Filas de items
        self.set_text_color(51, 65, 85)
        fill = False
        
        for det in self.venta.detalles:
            # Determinación de tipo y descripción
            if det.animal:
                codigo_a = getattr(det.animal, 'codigo', getattr(det.animal, 'codigo_identificacion', 'Animal'))
                nombre_a = getattr(det.animal, 'nombre', getattr(det.animal, 'raza', 'Pecuario'))
                desc = f"{codigo_a} - {nombre_a}"
                tipo_str = "Pecuario"
            elif det.insumo:
                desc = f"{det.insumo.nombre}"
                tipo_str = "Insumo"
            elif det.lote_origen and det.lote_origen.especie:
                desc = f"{det.lote_origen.especie.nombre_comun} (Lote #{det.lote_origen.codigo_lote or det.lote_origen.id})"
                tipo_str = "Planta / Cosecha"
            else:
                desc = "Producto General"
                tipo_str = "General"
                
            cant_str = f"{det.cantidad:g}"
            precio_str = f"${det.precio_venta_unitario:,.0f}"
            dcto_str = f"{det.descuento_pct:g}%" if det.descuento_pct else "-"
            subtot_str = f"${det.subtotal:,.0f}"
            
            # Altura y fondo
            bg_color = (248, 250, 252) if fill else (255, 255, 255)
            self.set_fill_color(*bg_color)
            self.set_draw_color(241, 245, 249)
            
            self.set_font('Helvetica', '', 8)
            self.cell(col_w[0], 6, clean_text(cant_str), border='B', align='C', fill=True)
            self.cell(col_w[1], 6, clean_text(desc[:45]), border='B', align='L', fill=True)
            self.cell(col_w[2], 6, clean_text(tipo_str), border='B', align='C', fill=True)
            self.cell(col_w[3], 6, clean_text(precio_str), border='B', align='R', fill=True)
            self.cell(col_w[4], 6, clean_text(dcto_str), border='B', align='C', fill=True)
            self.cell(col_w[5], 6, clean_text(subtot_str), border='B', align='R', fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            fill = not fill
            
        self.ln(4)

    def render_totales_y_cierre(self):
        y_pos = self.get_y()
        
        # Bloque Izquierdo: Observaciones & Condiciones
        self.set_xy(15, y_pos)
        self.set_font('Helvetica', 'B', 8)
        self.set_text_color(5, 150, 105)
        self.cell(100, 4, "OBSERVACIONES / NOTAS", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_font('Helvetica', '', 7)
        self.set_text_color(100, 116, 139)
        obs = self.venta.observaciones or "Mercancia revisada a satisfaccion. Garantia segun politicas del vivero/empresa."
        self.multi_cell(100, 3.5, clean_text(obs))
        
        if self.venta.tipo_venta == 'Credito':
            self.ln(2)
            self.set_font('Helvetica', 'B', 7)
            self.set_text_color(180, 83, 9) # Amber
            saldo_info = f"VENTA A CREDITO - Abono inicial: ${self.venta.abono:,.0f} | Saldo Pendiente: ${self.venta.saldo:,.0f}"
            self.cell(100, 4, clean_text(saldo_info), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Bloque Derecho: Resumen de Totales
        subtotal_val = self.venta.subtotal or sum(d.subtotal for d in self.venta.detalles)
        descuento_val = self.venta.descuento or 0.0
        impuestos_val = self.venta.impuestos or 0.0
        total_val = self.venta.total or subtotal_val
        
        box_x = 120
        box_w = 81
        
        self.set_xy(box_x, y_pos)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(71, 85, 105)
        
        self.cell(45, 5, "Subtotal:", align='R')
        self.cell(36, 5, f"${subtotal_val:,.0f}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        if descuento_val > 0:
            self.set_x(box_x)
            self.cell(45, 5, "Descuento General:", align='R')
            self.cell(36, 5, f"-${descuento_val:,.0f}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
        if impuestos_val > 0:
            self.set_x(box_x)
            self.cell(45, 5, "IVA / Impuestos:", align='R')
            self.cell(36, 5, f"+${impuestos_val:,.0f}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
        self.set_x(box_x)
        self.set_draw_color(5, 150, 105)
        self.set_fill_color(240, 253, 244) # Light emerald
        self.rect(box_x, self.get_y(), box_w, 9, 'FD')
        
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(5, 150, 105)
        self.cell(45, 9, "TOTAL A PAGAR:", align='R')
        self.cell(36, 9, f"${total_val:,.0f} COP", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Bloque CUFE DIAN si es factura electrónica
        if self.venta.es_electronica and self.venta.cufe:
            self.ln(3)
            self.set_x(15)
            self.set_draw_color(16, 185, 129)
            self.set_fill_color(240, 253, 244)
            self.rect(15, self.get_y(), 186, 14, 'FD')
            self.set_font('Helvetica', 'B', 7)
            self.set_text_color(6, 95, 70)
            self.cell(186, 4, clean_text("FACTURA ELECTRONICA DE VENTA - DIAN COLOMBIA (DOCUMENTO OFICIAL VALIDADO)"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font('Helvetica', '', 6)
            self.set_text_color(55, 65, 81)
            self.multi_cell(186, 3, clean_text(f"CUFE: {self.venta.cufe}"))
            fecha_dian_str = self.venta.fecha_emision_dian.strftime('%Y-%m-%d %H:%M:%S') if self.venta.fecha_emision_dian else 'En linea'
            self.cell(186, 3, clean_text(f"Fecha Validacion DIAN: {fecha_dian_str} | Estado: {self.venta.estado_dian} | {self.venta.dian_mensaje or 'Aceptado por DIAN'}"))



def generar_pdf_factura(venta):
    """Genera y retorna los bytes del PDF de la factura comercial."""
    pdf = FacturaComercialPDF(venta)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.render_cliente_info()
    pdf.render_items_table()
    pdf.render_totales_y_cierre()
    return bytes(pdf.output())


class CotizacionComercialPDF(FPDF):
    """Generador de presupuestos y cotizaciones comerciales en PDF."""
    def __init__(self, cotizacion):
        super().__init__(orientation='P', unit='mm', format='letter')
        self.cotizacion = cotizacion
        self.empresa = cotizacion.empresa
        self.cliente = cotizacion.cliente
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(15, 15, 15)

    def header(self):
        # Franja superior decorativa azul/esmeralda
        self.set_fill_color(2, 132, 199) # Azul comercial pro
        self.rect(0, 0, 216, 5, 'F')
        
        # Datos Empresa
        self.set_xy(15, 12)
        self.set_font('Helvetica', 'B', 15)
        self.set_text_color(30, 41, 59)
        nombre_empresa = self.empresa.nombre if self.empresa else "EcoSistem Agro"
        self.cell(115, 7, clean_text(nombre_empresa), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_font('Helvetica', '', 8)
        self.set_text_color(100, 116, 139)
        nit = f"NIT / RUT: {self.empresa.nit_rut}" if self.empresa and self.empresa.nit_rut else "NIT: Régimen Agropecuario"
        tel = f"Tel: {self.empresa.telefono}" if self.empresa and self.empresa.telefono else ""
        direc = f"Dir: {self.empresa.direccion}" if self.empresa and self.empresa.direccion else ""
        ciudad = f"{self.empresa.ciudad}" if self.empresa and self.empresa.ciudad else "Colombia"
        email = f"Email: {self.empresa.email}" if self.empresa and self.empresa.email else ""
        
        empresa_info = f"{nit} | {tel}\n{direc} - {ciudad}\n{email}"
        self.set_x(15)
        self.multi_cell(115, 4, clean_text(empresa_info))

        # Caja de Cotización (Derecha)
        self.set_xy(135, 12)
        self.set_fill_color(240, 249, 255)
        self.set_draw_color(186, 230, 253)
        self.rect(135, 12, 66, 28, 'FD')
        
        self.set_xy(135, 14)
        self.set_font('Helvetica', 'B', 12)
        self.set_text_color(3, 105, 161)
        self.cell(66, 5, clean_text("COTIZACIÓN COMERCIAL"), align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_font('Helvetica', 'B', 11)
        self.set_text_color(15, 23, 42)
        self.set_x(135)
        self.cell(66, 5, clean_text(f"No. {self.cotizacion.numero_cotizacion}"), align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_font('Helvetica', '', 7.5)
        self.set_text_color(71, 85, 105)
        self.set_x(135)
        fecha_str = self.cotizacion.fecha_creacion.strftime('%d/%m/%Y %H:%M') if self.cotizacion.fecha_creacion else '-'
        self.cell(66, 4, clean_text(f"Fecha Emisión: {fecha_str}"), align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        vence_str = self.cotizacion.fecha_vencimiento.strftime('%d/%m/%Y') if self.cotizacion.fecha_vencimiento else '15 días'
        self.set_x(135)
        self.cell(66, 4, clean_text(f"Válida Hasta: {vence_str}"), align='C')
        
        self.ln(12)

    def footer(self):
        self.set_y(-18)
        self.set_font('Helvetica', 'I', 7)
        self.set_text_color(148, 163, 184)
        self.cell(0, 4, clean_text("EcoSistem | Software de Gestión Agropecuaria & Viveros"), align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 4, clean_text(f"Página {self.page_no()}/{{nb}} - Propuesta económica confidencial sujeta a existencias"), align='C')

    def render_cliente_info(self):
        self.set_draw_color(226, 232, 240)
        self.set_fill_color(248, 250, 252)
        self.rect(15, self.get_y(), 186, 22, 'FD')
        
        y_ini = self.get_y() + 2.5
        self.set_xy(18, y_ini)
        self.set_font('Helvetica', 'B', 8)
        self.set_text_color(2, 132, 199)
        self.cell(90, 4, clean_text("INFORMACIÓN DEL CLIENTE / PROSPECTO"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_font('Helvetica', '', 8)
        self.set_text_color(51, 65, 85)
        nom = self.cliente.nombre if self.cliente else "Cliente General / Mostrador"
        doc = f"{self.cliente.tipo_documento or 'CC/NIT'}: {self.cliente.documento}" if self.cliente and self.cliente.documento else "NIT/CC: No registrado"
        self.set_x(18)
        self.cell(90, 4, clean_text(f"Nombre: {nom} | {doc}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        tel = f"Tel: {self.cliente.telefono}" if self.cliente and self.cliente.telefono else "Tel: N/A"
        dir_c = f"Dir: {self.cliente.direccion or 'N/A'}" if self.cliente else "Dir: N/A"
        self.set_x(18)
        self.cell(90, 4, clean_text(f"{tel} | {dir_c}"))
        
        # Estado de cotización
        self.set_xy(125, y_ini + 2)
        self.set_font('Helvetica', 'B', 8)
        self.set_text_color(71, 85, 105)
        self.cell(70, 4, clean_text(f"Estado: {self.cotizacion.estado.upper()}"), align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font('Helvetica', '', 7.5)
        asesor = self.cotizacion.usuario.nombre if self.cotizacion.usuario else "Asesor Comercial"
        self.set_x(125)
        self.cell(70, 4, clean_text(f"Atendido por: {asesor}"), align='R')
        
        self.set_y(y_ini + 22)

    def render_items_table(self):
        self.ln(2)
        # Encabezados
        self.set_fill_color(2, 132, 199)
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 8)
        
        col_w = [90, 22, 26, 22, 26]
        headers = ["DESCRIPCIÓN DE PRODUCTOS / SERVICIOS", "CANT", "PRECIO UNIT", "DCTO %", "SUBTOTAL"]
        
        for w, h in zip(col_w, headers):
            self.cell(w, 7, clean_text(h), border=0, align='C' if w in [22, 26] else 'L', fill=True)
        self.ln()

        # Filas
        self.set_text_color(30, 41, 59)
        self.set_font('Helvetica', '', 8)
        fill = False
        
        for d in self.cotizacion.detalles:
            if self.get_y() > 240:
                self.add_page()
                
            self.set_fill_color(248, 250, 252) if fill else self.set_fill_color(255, 255, 255)
            desc = d.descripcion or 'Producto / Labor'
            
            self.cell(col_w[0], 6.5, clean_text(desc[:55]), fill=fill)
            self.cell(col_w[1], 6.5, f"{d.cantidad:g}", align='C', fill=fill)
            self.cell(col_w[2], 6.5, f"${d.precio_unitario:,.0f}", align='R', fill=fill)
            dcto_txt = f"{d.descuento_pct:g}%" if d.descuento_pct else "-"
            self.cell(col_w[3], 6.5, dcto_txt, align='C', fill=fill)
            self.cell(col_w[4], 6.5, f"${d.subtotal:,.0f}", align='R', fill=fill)
            self.ln()
            fill = not fill

        self.set_draw_color(203, 213, 225)
        self.line(15, self.get_y(), 201, self.get_y())

    def render_totales_y_cierre(self):
        self.ln(4)
        y_start = self.get_y()
        
        # Bloque izquierdo: Observaciones y Condiciones Comerciales
        self.set_xy(15, y_start)
        self.set_fill_color(248, 250, 252)
        self.set_draw_color(226, 232, 240)
        self.rect(15, y_start, 100, 32, 'FD')
        
        self.set_xy(18, y_start + 2)
        self.set_font('Helvetica', 'B', 7.5)
        self.set_text_color(2, 132, 199)
        self.cell(94, 4, clean_text("CONDICIONES COMERCIALES & VALIDEZ:"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_font('Helvetica', '', 7)
        self.set_text_color(71, 85, 105)
        obs = self.cotizacion.observaciones or "1. Precios en pesos colombianos (COP).\n2. Disponibilidad de material vegetal sujeta a inventario.\n3. Transporte y flete a acordar."
        self.set_x(18)
        self.multi_cell(94, 3.5, clean_text(obs[:240]))

        # Bloque derecho: Totales
        box_x = 120
        box_w = 81
        self.set_xy(box_x, y_start)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(71, 85, 105)
        
        self.cell(45, 5, "Subtotal Base:", align='R')
        self.cell(36, 5, f"${self.cotizacion.subtotal:,.0f}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        if self.cotizacion.descuento > 0:
            self.set_x(box_x)
            self.set_text_color(220, 38, 38)
            self.cell(45, 5, "Descuento Comercial:", align='R')
            self.cell(36, 5, f"-${self.cotizacion.descuento:,.0f}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_text_color(71, 85, 105)
            
        if self.cotizacion.impuestos > 0:
            self.set_x(box_x)
            self.cell(45, 5, "IVA / Impuestos:", align='R')
            self.cell(36, 5, f"${self.cotizacion.impuestos:,.0f}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_x(box_x)
        self.set_fill_color(240, 249, 255)
        self.set_draw_color(186, 230, 253)
        self.rect(box_x, self.get_y(), box_w, 9, 'FD')
        
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(2, 132, 199)
        self.cell(45, 9, "TOTAL COTIZACIÓN:", align='R')
        self.cell(36, 9, f"${self.cotizacion.total:,.0f} COP", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def generar_pdf_cotizacion(cotizacion):
    """Genera y retorna los bytes del PDF de una cotización."""
    pdf = CotizacionComercialPDF(cotizacion)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.render_cliente_info()
    pdf.render_items_table()
    pdf.render_totales_y_cierre()
    return bytes(pdf.output())


class ReciboCajaAbonoPDF(FPDF):
    """Generador de Comprobantes de Abono / Recibo de Caja en PDF."""
    def __init__(self, abono):
        super().__init__(orientation='P', unit='mm', format='letter')
        self.abono = abono
        self.empresa = abono.empresa
        self.venta = abono.venta
        self.cliente = abono.cliente or abono.venta.cliente
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margins(15, 15, 15)

    def header(self):
        # Franja superior verde
        self.set_fill_color(16, 185, 129)
        self.rect(0, 0, 216, 5, 'F')
        
        # Datos Empresa
        self.set_xy(15, 12)
        self.set_font('Helvetica', 'B', 15)
        self.set_text_color(30, 41, 59)
        nombre_empresa = self.empresa.nombre if self.empresa else "EcoSistem Agro"
        self.cell(115, 7, clean_text(nombre_empresa), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_font('Helvetica', '', 8)
        self.set_text_color(100, 116, 139)
        nit = f"NIT: {self.empresa.nit_rut}" if self.empresa and self.empresa.nit_rut else "NIT: Régimen Agropecuario"
        tel = f"Tel: {self.empresa.telefono}" if self.empresa and self.empresa.telefono else ""
        direc = f"Dir: {self.empresa.direccion}" if self.empresa and self.empresa.direccion else ""
        empresa_info = f"{nit} | {tel}\n{direc}"
        self.set_x(15)
        self.multi_cell(115, 4, clean_text(empresa_info))

        # Caja de Recibo (Derecha)
        self.set_xy(135, 12)
        self.set_fill_color(240, 253, 244)
        self.set_draw_color(167, 243, 208)
        self.rect(135, 12, 66, 26, 'FD')
        
        self.set_xy(135, 14)
        self.set_font('Helvetica', 'B', 11)
        self.set_text_color(5, 150, 105)
        self.cell(66, 5, clean_text("RECIBO DE CAJA / ABONO"), align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_font('Helvetica', 'B', 11)
        self.set_text_color(15, 23, 42)
        self.set_x(135)
        self.cell(66, 5, clean_text(f"No. {self.abono.numero_recibo}"), align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_font('Helvetica', '', 8)
        self.set_text_color(71, 85, 105)
        self.set_x(135)
        fecha_str = self.abono.fecha.strftime('%d/%m/%Y %H:%M') if self.abono.fecha else '-'
        self.cell(66, 4, clean_text(f"Fecha: {fecha_str}"), align='C')
        
        self.ln(10)

    def render_cuerpo(self):
        # Datos del Cliente y Factura
        self.set_fill_color(248, 250, 252)
        self.set_draw_color(226, 232, 240)
        self.rect(15, self.get_y(), 186, 24, 'FD')
        
        y_c = self.get_y() + 3
        self.set_xy(18, y_c)
        self.set_font('Helvetica', 'B', 8.5)
        self.set_text_color(5, 150, 105)
        self.cell(90, 4, clean_text("RECIBIDO DE:"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_font('Helvetica', '', 8.5)
        self.set_text_color(30, 41, 59)
        nom = self.cliente.nombre if self.cliente else "Cliente General"
        doc = f"{self.cliente.tipo_documento or 'CC'}: {self.cliente.documento}" if self.cliente and self.cliente.documento else ""
        self.set_x(18)
        self.cell(90, 4, clean_text(f"{nom} | {doc}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_x(18)
        self.cell(90, 4, clean_text(f"Concepto: Abono a Factura de Venta #{self.venta.numero_factura}"))
        
        # Caja derecha: Forma de Pago y Cajero
        self.set_xy(120, y_c)
        self.set_font('Helvetica', 'B', 8)
        self.set_text_color(71, 85, 105)
        self.cell(75, 4, clean_text(f"Medio de Pago: {self.abono.metodo_pago.upper()}"), align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        cajero = self.abono.usuario.nombre if self.abono.usuario else "Cajero"
        self.set_x(120)
        self.cell(75, 4, clean_text(f"Recibido por: {cajero}"), align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if self.abono.caja_turno_id:
            self.set_x(120)
            self.cell(75, 4, clean_text(f"Turno de Caja: #{self.abono.caja_turno_id}"), align='R')

        self.set_y(y_c + 24)
        self.ln(6)

        # Tabla de Conciliación de Cartera
        self.set_fill_color(5, 150, 105)
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 8.5)
        
        col_w = [46, 46, 46, 48]
        hdrs = ["SALDO ANTERIOR", "VALOR ABONADO", "NUEVO SALDO PENDIENTE", "ESTADO DEUDA"]
        for w, h in zip(col_w, hdrs):
            self.cell(w, 7, clean_text(h), align='C', fill=True)
        self.ln()

        self.set_fill_color(255, 255, 255)
        self.set_text_color(15, 23, 42)
        self.set_font('Helvetica', 'B', 10)
        
        self.cell(col_w[0], 9, f"${self.abono.saldo_anterior:,.0f}", align='C', border='B')
        self.set_text_color(16, 185, 129)
        self.cell(col_w[1], 9, f"${self.abono.monto:,.0f}", align='C', border='B')
        self.set_text_color(220, 38, 38) if self.abono.saldo_nuevo > 0 else self.set_text_color(5, 150, 105)
        self.cell(col_w[2], 9, f"${self.abono.saldo_nuevo:,.0f}", align='C', border='B')
        
        estado_txt = "SALDADA / PAGADA" if self.abono.saldo_nuevo <= 0 else "CON SALDO PENDIENTE"
        self.set_font('Helvetica', 'B', 8)
        self.cell(col_w[3], 9, clean_text(estado_txt), align='C', border='B')
        self.ln(12)

        if self.abono.notas:
            self.set_font('Helvetica', 'I', 8)
            self.set_text_color(100, 116, 139)
            self.cell(186, 5, clean_text(f"Observaciones: {self.abono.notas}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(6)

        # Firmas
        self.ln(15)
        y_firmas = self.get_y()
        self.set_draw_color(148, 163, 184)
        self.line(25, y_firmas, 85, y_firmas)
        self.line(125, y_firmas, 185, y_firmas)
        
        self.set_xy(25, y_firmas + 2)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(71, 85, 105)
        self.cell(60, 4, clean_text("Firma Recibido (Cajero / Empresa)"), align='C')
        
        self.set_xy(125, y_firmas + 2)
        self.cell(60, 4, clean_text("Firma Entregado (Cliente / Pagador)"), align='C')


def generar_pdf_recibo_abono(abono):
    """Genera y retorna los bytes del PDF de un recibo de caja / abono."""
    pdf = ReciboCajaAbonoPDF(abono)
    pdf.add_page()
    pdf.render_cuerpo()
    return bytes(pdf.output())
