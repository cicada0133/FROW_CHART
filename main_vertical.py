import sys
import os
import schemdraw
import re
from schemdraw import flow
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from tree_sitter import Language, Parser
import tree_sitter_cpp as tscpp
import textwrap

# Monkey-patch schemdraw to handle special characters in labels during size measurement
import schemdraw.flow.flow
import schemdraw.backends.svg as schem_svg

_original_labelsize = schemdraw.flow.flow.labelsize
def _safe_labelsize(label, pad=0.125):
    if hasattr(label, 'label') and isinstance(label.label, str):
        original_text = label.label
        label.label = original_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        try:
            res = _original_labelsize(label, pad)
        finally:
            label.label = original_text
        return res
    return _original_labelsize(label, pad)
schemdraw.flow.flow.labelsize = _safe_labelsize

_original_text_size = schem_svg.text_size
def _safe_text_size(text, font=None, size=14, **kwargs):
    if isinstance(text, str):
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return _original_text_size(text, font=font, size=size, **kwargs)
schem_svg.text_size = _safe_text_size


def get_cpp_parser():
    CPP_LANGUAGE = Language(tscpp.language())
    parser = Parser(CPP_LANGUAGE)
    return parser

class PreProcess(flow.Box):
    """GOST Predefined Process (Procedure call)"""
    def __init__(self, *args, **kwargs):
        kwargs['fill'] = kwargs.get('fill', 'white')
        super().__init__(*args, **kwargs)

import schemdraw.segments as schemseg
from schemdraw.elements import Element

class Preparation(Element):
    """ГОСТ: Шестиугольник для циклов for (горизонтальный)"""
    def __init__(self, w=10, h=4, **kwargs):
        super().__init__(**kwargs)
        # Рассчитываем точки относительно центра (0,0)
        # Чтобы он был горизонтальным, уголки должны быть по бокам (E и W)
        slant = min(h/2, w/4, 2.0)
        x0, x1, x2, x3 = -w/2, -w/2 + slant, w/2 - slant, w/2
        y0, y1 = -h/2, h/2
        
        # Точки: левый уголок, верхний край, правый уголок, нижний край
        v = [(x0, 0), (x1, y1), (x2, y1), (x3, 0), (x2, y0), (x1, y0)]
        self.segments.append(schemseg.SegmentPoly(v))
        
        # Анкоры для соединения (N - вход сверху, S - выход снизу)
        self.anchors["N"] = (0, y1)
        self.anchors["S"] = (0, y0)
        self.anchors["W"] = (x0, 0)
        self.anchors["E"] = (x3, 0)
        self.bbox = ((x0, y0), (x3, y1))

class VerticalMainRenderer:
    def __init__(self, staggered=False, config=None):
        self.staggered = staggered
        self.config = config if config else {}
        self.return_starts = []
        self.max_highway_x = 0.0
        self.d = schemdraw.Drawing(show=False, canvas='matplotlib')
        import logging
        logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
        
        self.font_size = self.config.get('font_size', 79)
        plt.rcParams.update({'font.size': self.font_size, 'axes.labelsize': self.font_size, 'xtick.labelsize': self.font_size, 'ytick.labelsize': self.font_size})
        plt.rcParams['font.family'] = 'System'
        plt.rcParams['font.weight'] = 'bold'
        
        self.d.config(fontsize=self.font_size, margin=2.5, lw=10, font='System')
        
        # Парсим параметры (переводим "пиксели" в абстрактные единицы schemdraw)
        vert_int = self.config.get('vert_spacing', 10) / 5.5  # 10 -> ~1.8
        horiz_int = self.config.get('horiz_spacing', 10) * 12.0 # 10 -> 120.0
        pad = self.config.get('padding', 3) * 1.5           # Отступы
        
        self.scale = vert_int
        self.axis_x = 0.0
        self.last_pos = (self.axis_x, 0)
        self.max_y = 0
        self.merge_gap = 5.0
        
        # Highway tracking
        self.case_highway_x = horiz_int
        self.exit_highway_x = self.case_highway_x + horiz_int
        self.final_terminal = None
        
        self.text_max_width = int(self.config.get('max_width', 200) / 8.0) # approx 25 chars
        self.pad_w = pad + 3.0
        self.pad_h = pad + 1.5

    def wrap_text(self, text, max_width=None):
        if not text: return ""
        mw = max_width if max_width else self.text_max_width
        return "\n".join(textwrap.wrap(text, width=mw))

    def add_block(self, ntype, label, at=None, skip_line=False, anchor=None, direction='down'):
        text = self.wrap_text(label)
        if at is None:
            at = self.last_pos

        if not skip_line:
            line = flow.Line().at(at)
            if direction == 'down':
                line.down(self.scale)
            elif direction == 'right':
                line.right(self.scale)
            elif direction == 'left':
                line.left(self.scale)
            l_obj = self.d.add(line)
            at = l_obj.end

        lines = text.split('\n')
        max_len = max(len(ln) for ln in lines) if lines else 0
        char_w = 1.35
        base_w = max_len * char_w + self.pad_w
        w = max(self.pad_w * 2, base_w)
        h = self.pad_h + (len(lines) - 1) * 2.1

        kwargs = {'at': at, 'label': text}
        if anchor: kwargs['anchor'] = anchor
        if self.config.get('fill_blocks', True):
            kwargs['fill'] = 'white'
            kwargs['zorder'] = 10

        if ntype in ['start', 'end', 'Начало', 'Конец', 'Terminal']:
            obj = flow.Terminal(w=max(18.0, w), h=6.0, **kwargs)
        elif ntype == 'for_loop':
            # Очищаем kwargs от label, чтобы не было двоения текста
            clean_kwargs = {k:v for k,v in kwargs.items() if k != 'label'}
            # Явно задаем theta=0, чтобы библиотек не вращала блок при движении down
            obj = Preparation(w=w + 10.0, h=6.0, theta=0, **clean_kwargs).label(text, fontsize=self.font_size, loc='center')
        elif ntype == 'decision' or ntype in ['if', 'while', 'choice', 'while_loop']:
            obj = flow.Decision(w=w*1.5, h=h+4.0, **kwargs)
        elif ntype == 'io':
            obj = flow.Data(w=w+4.0, h=h, **kwargs)
        elif ntype == 'call':
            obj = PreProcess(w=w, h=h, **kwargs)
            obj = self.d.add(obj)
            offset = 2.1
            if abs(obj.NW[1] - obj.SW[1]) > 0.1:
                self.d.add(flow.Line().at((obj.NW[0] + offset, obj.NW[1])).to((obj.NW[0] + offset, obj.SW[1])))
                self.d.add(flow.Line().at((obj.NE[0] - offset, obj.NE[1])).to((obj.NE[0] - offset, obj.SE[1])))
        else:
            obj = flow.Box(w=w, h=h, **kwargs)
        
        if ntype != 'call':
            obj = self.d.add(obj)

        if direction == 'down':
            self.last_pos = (self.axis_x, float(obj.S[1]))
        elif direction == 'right':
            self.last_pos = (float(obj.E[0]), float(obj.E[1]))
        elif direction == 'left':
            self.last_pos = (float(obj.W[0]), float(obj.W[1]))
            
        self.max_y = min(self.max_y, float(obj.S[1]))
        
        if ntype in ['end', 'Конец', 'Terminal']:
            self.final_terminal = obj
            
        return obj

    def render_nodes(self, nodes, is_first=False, anchor=None, direction='down'):
        if is_first:
            self.axis_x = self.last_pos[0]
            
        is_terminated = False
        has_ended = False
        for i, node in enumerate(nodes):
            if is_terminated and node[0] not in ['end', 'Конец']: 
                break
            
            ntype = node[0]
            if ntype in ['end', 'Конец']:
                if has_ended:
                    break
                has_ended = True
                
                trunk_x = 0.0
                bot_y = self.max_y - self.scale * 3.0
                end_pos = (trunk_x, bot_y)
                
                if not is_terminated:
                    p1 = self.last_pos
                    if abs(p1[0] - trunk_x) > 0.1:
                        self.d.add(flow.Line().at(p1).to((p1[0], bot_y + 4.0)))
                        self.d.add(flow.Line().at((p1[0], bot_y + 4.0)).to((trunk_x, bot_y + 4.0)))
                        self.d.add(flow.Line(arrow='->').at((trunk_x, bot_y + 4.0)).to(end_pos))
                    else:
                        self.d.add(flow.Line(arrow='->').at(p1).to(end_pos))
                
                self.last_pos = end_pos
                obj = self.add_block(ntype, node[1], skip_line=True, anchor='N', direction='down')
                obj_N = obj.N
                
                wide_route = self.config.get('return_wide_route', False)
                highway_x = self.max_highway_x + self.case_highway_x
                descent = self.scale * 0.5  # сначала вниз перед поворотом вправо
                for ret_pos in self.return_starts:
                    ret_x = float(ret_pos[0])
                    ret_y = float(ret_pos[1])
                    via_y = bot_y + 5.0
                    if abs(ret_x - trunk_x) < 0.1:
                        # Блок по центру: прямо вниз
                        self.d.add(flow.Line(arrow='->').at(ret_pos).to(obj_N))
                    elif ret_x > trunk_x and wide_route:
                        # Блок справа + режим обхода: вниз чуть-чуть, затем вправо, вниз, влево
                        mid_y = ret_y - descent
                        self.d.add(flow.Line().at(ret_pos).to((ret_x, mid_y)))
                        self.d.add(flow.Line().at((ret_x, mid_y)).to((highway_x, mid_y)))
                        self.d.add(flow.Line().at((highway_x, mid_y)).to((highway_x, via_y)))
                        self.d.add(flow.Line().at((highway_x, via_y)).to((trunk_x, via_y)))
                        self.d.add(flow.Line(arrow='->').at((trunk_x, via_y)).to(obj_N))
                    else:
                        # Обычный маршрут: вниз до via_y, затем к центру
                        self.d.add(flow.Line().at(ret_pos).to((ret_x, via_y)))
                        self.d.add(flow.Line().at((ret_x, via_y)).to((trunk_x, via_y)))
                        self.d.add(flow.Line(arrow='->').at((trunk_x, via_y)).to(obj_N))
                
                continue
                
            if ntype in ['statement', 'call', 'io', 'start']:
                obj = self.add_block(ntype, node[1], skip_line=is_first, anchor=anchor, direction=direction)
                is_first = False
                anchor = None 
                if direction == 'right': is_first = False 
            
            elif ntype == 'while':
                cond = node[1]
                body_nodes = node[2]

                # небольшой отступ для того, чтобы линия возврата не наезжала
                l_pad = self.d.add(flow.Line().at(self.last_pos).down(2.0))
                self.last_pos = l_pad.end
                target_entry = self.last_pos
                
                dia = self.add_block('decision', cond, skip_line=True, anchor='N', direction='down')
                is_first = False
                trunk_x = float(dia.S[0])
                trunk_y = float(dia.S[1])
                
                # Ветка Нет (справа)
                highway_right = trunk_x + self.case_highway_x * 2.0
                self.max_highway_x = max(self.max_highway_x, highway_right)
                l_no = self.d.add(flow.Line().at(dia.E).to((highway_right, dia.E[1])).label('Нет', loc='top', fontsize=self.font_size, ofst=2.5))
                pos_alt = l_no.end
                
                # Ветка Да (вниз)
                l_yes = self.d.add(flow.Line().at(dia.S).down(self.scale).label('Да', loc='start', fontsize=self.font_size, ofst=(3.0, -5.0)))
                self.last_pos = l_yes.end
                
                term_body = self.render_nodes(body_nodes, is_first=True, anchor='N', direction='down')
                bot_y = self.max_y - 8.0
                
                if not term_body:
                    # Цикл возвращается наверх (по левой стороне)
                    highway_left = trunk_x - self.case_highway_x * 2.0
                    
                    cur_pos = self.last_pos
                    self.d.add(flow.Line().at(cur_pos).to((cur_pos[0], bot_y + 2.0)))
                    self.d.add(flow.Line().at((cur_pos[0], bot_y + 2.0)).to((highway_left, bot_y + 2.0)))
                    self.d.add(flow.Line().at((highway_left, bot_y + 2.0)).to((highway_left, float(target_entry[1]))))
                    self.d.add(flow.Line(arrow='->').at((highway_left, float(target_entry[1]))).to(target_entry))

                # Ветка Нет опускается вниз и становится новым стволом
                self.d.add(flow.Line().at(pos_alt).to((highway_right, bot_y)))
                self.d.add(flow.Line().at((highway_right, bot_y)).to((trunk_x, bot_y)))
                
                self.last_pos = (trunk_x, bot_y)
                self.max_y = min(self.max_y, bot_y)

            elif ntype == 'for_loop':
                cond_txt = node[1]
                body_nodes = node[2]

                # 1. Заголовок цикла (Шестиугольник)
                # Делаем отступ из двух сегментов, чтобы точка входа (возврат) была выше блока
                l_pad_top = self.d.add(flow.Line().at(self.last_pos).down(2.0))
                target_entry = l_pad_top.end # Точка возврата теперь тут (над блоком)
                l_pad_bot = self.d.add(flow.Line().at(target_entry).down(2.0))
                self.last_pos = l_pad_bot.end
                
                dia = self.add_block('for_loop', cond_txt, skip_line=True, anchor='N', direction='down')
                trunk_x = float(dia.S[0])
                
                # Ветка Нет (справа) - выход из цикла
                highway_right = trunk_x + self.case_highway_x * 2.0
                self.max_highway_x = max(self.max_highway_x, highway_right)
                l_no = self.d.add(flow.Line().at(dia.E).to((highway_right, dia.E[1])))
                pos_alt = l_no.end
                
                # Ветка Да (вниз) - вход в тело
                l_yes = self.d.add(flow.Line().at(dia.S).down(self.scale))
                self.last_pos = l_yes.end
                
                # Тело цикла
                term_body = self.render_nodes(body_nodes, is_first=True, anchor='N', direction='down')
                
                bot_y = self.max_y - 8.0
                
                # Возврат к началу (слева)
                highway_left = trunk_x - self.case_highway_x * 2.0
                cur_pos = self.last_pos
                self.d.add(flow.Line().at(cur_pos).to((cur_pos[0], bot_y + 2.0)))
                self.d.add(flow.Line().at((cur_pos[0], bot_y + 2.0)).to((highway_left, bot_y + 2.0)))
                self.d.add(flow.Line().at((highway_left, bot_y + 2.0)).to((highway_left, float(target_entry[1]))))
                self.d.add(flow.Line(arrow='->').at((highway_left, float(target_entry[1]))).to(target_entry))

                # Ветка выхода опускается вниз и становится новым стволом
                self.d.add(flow.Line().at(pos_alt).to((highway_right, bot_y)))
                self.d.add(flow.Line().at((highway_right, bot_y)).to((trunk_x, bot_y)))
                
                self.last_pos = (trunk_x, bot_y)
                is_first = False
                anchor = 'N'
                self.max_y = min(self.max_y, bot_y)

            elif ntype == 'do_while':
                cond = node[1]
                body_nodes = node[2]
                
                l_pad = self.d.add(flow.Line().at(self.last_pos).down(2.0))
                self.last_pos = l_pad.end
                target_entry = self.last_pos
                
                term_body = self.render_nodes(body_nodes, is_first=True, anchor='N', direction='down')
                is_first = False
                
                dia = self.add_block('decision', cond, skip_line=False)
                trunk_x = float(dia.S[0])
                trunk_y = float(dia.S[1])
                
                # Ветка Да (возврат вверх по левой стороне)
                highway_left = trunk_x - self.case_highway_x * 2.0
                l_yes = self.d.add(flow.Line().at(dia.W).to((highway_left, dia.W[1])).label('Да', loc='top', fontsize=self.font_size, ofst=2.5))
                
                self.d.add(flow.Line().at(l_yes.end).to((highway_left, float(target_entry[1]))))
                self.d.add(flow.Line(arrow='->').at((highway_left, float(target_entry[1]))).to(target_entry))
                
                # Ветка Нет (вниз)
                l_no = self.d.add(flow.Line().at(dia.S).down(self.scale).label('Нет', loc='start', fontsize=self.font_size, ofst=(3.0, -5.0)))
                self.last_pos = l_no.end
                self.max_y = min(self.max_y, float(l_no.end[1]))

                # Do not set is_terminated = True here, so the next AST statements (clear, return) render underneath 'Да'

            elif ntype == 'if':
                cond = node[1]
                cons_nodes = node[2]
                alt_nodes = node[3] if len(node) > 3 else []
                
                dia = self.add_block('decision', cond, skip_line=is_first, anchor=anchor, direction=direction)
                is_first = False
                
                trunk_x = float(dia.S[0])
                trunk_y = float(dia.S[1])
                
                # Да branch (Right)
                highway_right = trunk_x + self.case_highway_x
                self.max_highway_x = max(self.max_highway_x, highway_right)
                l_yes = self.d.add(flow.Line().at(dia.E).to((highway_right, dia.E[1])).label('Да', loc='top', fontsize=self.font_size, ofst=2.5))
                self.last_pos = l_yes.end
                
                target_y = float(dia.S[1]) - self.scale
                l_yes_down = self.d.add(flow.Line().at(self.last_pos).to((highway_right, target_y)))
                self.last_pos = l_yes_down.end
                
                old_axis = self.axis_x
                self.axis_x = highway_right
                term_cons = self.render_nodes(cons_nodes, is_first=True, anchor='N', direction='down')
                pos_cons = self.last_pos
                self.axis_x = old_axis
                
                # Нет branch 
                if alt_nodes:
                    highway_left = trunk_x - self.case_highway_x
                    l_no = self.d.add(flow.Line().at(dia.W).to((highway_left, dia.W[1])).label('Нет', loc='top', fontsize=self.font_size, ofst=2.5))
                    self.last_pos = l_no.end
                    l_no_down = self.d.add(flow.Line().at(self.last_pos).to((highway_left, target_y)))
                    self.last_pos = l_no_down.end
                    
                    self.axis_x = highway_left
                    term_alt = self.render_nodes(alt_nodes, is_first=True, anchor='N', direction='down')
                    pos_alt = self.last_pos
                    self.axis_x = old_axis
                else:
                    l_no = self.d.add(flow.Line().at(dia.S).down(self.scale).label('Нет', loc='start', fontsize=self.font_size, ofst=(3.0, -5.0)))
                    pos_alt = l_no.end
                    term_alt = False
                    
                bot_y = min(self.max_y, float(pos_cons[1]), float(pos_alt[1])) - 10.0
                
                if not term_cons:
                    # branch Да line to bot
                    if abs(float(pos_cons[1]) - bot_y) > 0.1:
                        self.d.add(flow.Line().at(pos_cons).to((pos_cons[0], bot_y)))
                    # to trunk
                    self.d.add(flow.Line().at((pos_cons[0], bot_y)).to((trunk_x, bot_y)))
                
                if not term_alt:
                    # branch Нет line to bot
                    if abs(float(pos_alt[1]) - bot_y) > 0.1:
                        self.d.add(flow.Line().at(pos_alt).to((pos_alt[0], bot_y)))
                    if abs(pos_alt[0] - trunk_x) > 0.1:
                        self.d.add(flow.Line().at((pos_alt[0], bot_y)).to((trunk_x, bot_y)))
                
                if term_cons and term_alt:
                    is_terminated = True
                else:
                    self.last_pos = (trunk_x, bot_y)
                
                self.max_y = min(self.max_y, bot_y)

            elif ntype == 'switch':
                self.render_switch_vertical(node[1])
                is_first = False
                anchor = None

            elif ntype == 'return':
                obj = self.add_block('statement', node[1], skip_line=is_first, anchor=anchor, direction=direction)
                is_terminated = True
                self.return_starts.append(self.last_pos)

        return is_terminated

    def render_switch_vertical(self, cases):
        choice_dia = self.add_block('choice', 'choice', skip_line=False)
        current_y = float(choice_dia.S[1])
        trunk_x = float(choice_dia.S[0])
        
        if self.staggered:
            self._render_staggered_switch(cases, current_y, trunk_x)
        else:
            self._render_original_switch(cases, current_y, trunk_x)


    def _render_original_switch(self, cases, current_y, trunk_x):
        case_v_step = 16.0 
        right_offset = 20.0 
        highway_x = self.case_highway_x

        for i, case in enumerate(cases):
            label = case[0]
            nodes = case[1]
            row_y = current_y - (i + 1) * case_v_step
            start_y = current_y if i==0 else current_y - i*case_v_step
            
            if abs(start_y - row_y) > 0.1:
                self.d.add(flow.Line().at((trunk_x, start_y)).to((trunk_x, row_y)))
            
            self.d.add(flow.Line().at((trunk_x, row_y)).right(10.0).label(label, loc='top', fontsize=self.font_size, ofst=2.5))
            self.d.add(flow.Line().at((trunk_x+10.0, row_y)).to((trunk_x + right_offset, row_y)))
            
            self.last_pos = (trunk_x + right_offset, row_y)
            old_axis = self.axis_x
            self.axis_x = trunk_x + right_offset
            self.render_nodes(nodes, is_first=True, anchor='W', direction='right')
            
            if abs(float(self.last_pos[0]) - highway_x) > 0.1:
                self.d.add(flow.Line().at(self.last_pos).to((highway_x, float(self.last_pos[1]))))
            
            self.axis_x = old_axis
            self.max_y = min(self.max_y, float(self.last_pos[1]))

        top_y = current_y - case_v_step
        bot_y = self.max_y - 12.0
        if abs(top_y - bot_y) > 0.1:
            self.d.add(flow.Line().at((highway_x, top_y)).to((highway_x, bot_y)))
        
        # Connect the highway back to the main trunk point
        self.d.add(flow.Line().at((highway_x, bot_y)).to((trunk_x, bot_y)))
        
        # CONTINUATION OF MAIN TRUNK
        last_case_y = current_y - len(cases) * case_v_step
        if bot_y < last_case_y - 0.1:
            self.d.add(flow.Line().at((trunk_x, last_case_y)).to((trunk_x, bot_y)))
        
        self.last_pos = (trunk_x, bot_y) 
        self.max_y = min(self.max_y, bot_y)

    def _render_staggered_switch(self, cases, current_y, trunk_x):
        case_v_step = 8.0 
        side_offset = 20.0 
        highway_x_right = self.case_highway_x
        highway_x_left = -self.case_highway_x

        for i, case in enumerate(cases):
            label = case[0]
            nodes = case[1]
            row_y = current_y - (i + 1) * case_v_step
            start_y = current_y if i==0 else current_y - i*case_v_step
            
            if abs(start_y - row_y) > 0.1:
                self.d.add(flow.Line().at((trunk_x, start_y)).to((trunk_x, row_y)))
            
            is_right = (i % 2 == 0)
            
            if is_right:
                self.d.add(flow.Line().at((trunk_x, row_y)).right(10.0).label(label, loc='top', fontsize=self.font_size, ofst=2.5))
                self.d.add(flow.Line().at((trunk_x+10.0, row_y)).to((trunk_x + side_offset, row_y)))
                self.last_pos = (trunk_x + side_offset, row_y)
                
                old_axis = self.axis_x
                self.axis_x = trunk_x + side_offset
                self.render_nodes(nodes, is_first=True, anchor='W', direction='right')
                
                if abs(float(self.last_pos[0]) - highway_x_right) > 0.1:
                    self.d.add(flow.Line().at(self.last_pos).to((highway_x_right, float(self.last_pos[1]))))
                self.axis_x = old_axis
                
            else:
                self.d.add(flow.Line().at((trunk_x, row_y)).left(10.0).label(label, loc='top', fontsize=self.font_size, ofst=2.5))
                self.d.add(flow.Line().at((trunk_x-10.0, row_y)).to((trunk_x - side_offset, row_y)))
                self.last_pos = (trunk_x - side_offset, row_y)
                
                old_axis = self.axis_x
                self.axis_x = trunk_x - side_offset
                self.render_nodes(nodes, is_first=True, anchor='E', direction='left')
                
                if abs(float(self.last_pos[0]) - highway_x_left) > 0.1:
                    self.d.add(flow.Line().at(self.last_pos).to((highway_x_left, float(self.last_pos[1]))))
                self.axis_x = old_axis

            self.max_y = min(self.max_y, float(self.last_pos[1]))

        top_y = current_y - case_v_step
        bot_y = self.max_y - 12.0
        
        # Draw both highways
        if abs(top_y - bot_y) > 0.1:
            self.d.add(flow.Line().at((highway_x_right, top_y)).to((highway_x_right, bot_y)))
            # Left highway starts slightly lower so it doesn't float
            self.d.add(flow.Line().at((highway_x_left, current_y - 2*case_v_step)).to((highway_x_left, bot_y)))
        
        # Connect the highways back to the main trunk point
        self.d.add(flow.Line().at((highway_x_right, bot_y)).to((trunk_x, bot_y)))
        self.d.add(flow.Line().at((highway_x_left, bot_y)).to((trunk_x, bot_y)))
        
        # CONTINUATION OF MAIN TRUNK
        last_case_y = current_y - len(cases) * case_v_step
        if bot_y < last_case_y - 0.1:
            self.d.add(flow.Line().at((trunk_x, last_case_y)).to((trunk_x, bot_y)))
        
        self.last_pos = (trunk_x, bot_y) 
        self.max_y = min(self.max_y, bot_y)

    def save(self, filename):
        self.d.draw()
        self.d.save(filename, transparent=False)
        plt.close('all')

def process_single_node(node, code_bytes):
    if node.type == 'expression_statement':
        txt = code_bytes[node.start_byte:node.end_byte].decode('utf8').strip(';').strip()
        txt = re.sub(r'\s+', ' ', txt)
        if 'cin >>' in txt or 'cout <<' in txt:
            return [('io', txt)]
        elif '(' in txt and ')' in txt:
            return [('call', txt)]
        else:
            return [('statement', txt)]
    elif node.type == 'declaration':
        txt = code_bytes[node.start_byte:node.end_byte].decode('utf8').strip(';').strip()
        txt = re.sub(r'\s+', ' ', txt)
        return [('statement', txt)]
    elif node.type == 'while_statement':
        cond_node = node.child_by_field_name('condition')
        cond = code_bytes[cond_node.start_byte:cond_node.end_byte].decode('utf8').strip('()').strip()
        body = node.child_by_field_name('body')
        return [('while', cond, process_compound(body, code_bytes))]
    elif node.type == 'do_statement':
        cond_node = node.child_by_field_name('condition')
        cond = code_bytes[cond_node.start_byte:cond_node.end_byte].decode('utf8').strip('()').strip()
        body = node.child_by_field_name('body')
        return [('do_while', cond, process_compound(body, code_bytes))]
    elif node.type == 'if_statement':
        cond_node = node.child_by_field_name('condition')
        cond = code_bytes[cond_node.start_byte:cond_node.end_byte].decode('utf8').strip('()').strip()
        cons = node.child_by_field_name('consequence')
        alt_wrapper = node.child_by_field_name('alternative')
        
        alt = None
        if alt_wrapper:
            for child in alt_wrapper.children:
                if child.type != 'else':
                    alt = child
                    break
                    
        return [('if', cond, process_compound(cons, code_bytes), process_compound(alt, code_bytes))]
    elif node.type == 'switch_statement':
        body = node.child_by_field_name('body')
        cases = []
        for bchild in body.children:
            if bchild.type == 'case_statement':
                val_node = bchild.child_by_field_name('value')
                val = code_bytes[val_node.start_byte:val_node.end_byte].decode('utf8') if val_node else ""
                case_body = []
                for sub in bchild.children:
                    if sub.type not in [':', 'case', 'value', 'break_statement']:
                        case_body.extend(process_single_node(sub, code_bytes))
                cases.append((val, case_body))
            elif bchild.type == 'default_statement':
                case_body = []
                for sub in bchild.children:
                    if sub.type not in [':', 'default', 'break_statement']:
                        case_body.extend(process_single_node(sub, code_bytes))
                cases.append(('default', case_body))
        return [('switch', cases)]
    elif node.type == 'for_statement':
        init_node = node.child_by_field_name('initializer')
        cond_node = node.child_by_field_name('condition')
        update_node = node.child_by_field_name('update')
        body_node = node.child_by_field_name('body')
        
        init_txt = code_bytes[init_node.start_byte:init_node.end_byte].decode('utf8').replace(';', '').strip() if init_node else ""
        cond_txt = code_bytes[cond_node.start_byte:cond_node.end_byte].decode('utf8').strip() if cond_node else ""
        update_txt = code_bytes[update_node.start_byte:update_node.end_byte].decode('utf8').strip() if update_node else ""
        
        full_cond = f"{init_txt}; {cond_txt}; {update_txt}"
        return [('for_loop', full_cond, process_compound(body_node, code_bytes))]
    elif node.type == 'return_statement':
        txt = code_bytes[node.start_byte:node.end_byte].decode('utf8').strip(';').strip()
        txt = re.sub(r'\s+', ' ', txt)
        return [('return', txt)]
    elif node.type == 'compound_statement':
        return process_compound(node, code_bytes)
    return []

def process_compound(node, code_bytes):
    if not node: return []
    extracted = []
    if node.type in ['compound_statement', 'case_statement', 'default_statement']:
        for child in node.children:
            if child.type not in [':', 'case', 'value', 'default', '{', '}']:
                extracted.extend(process_single_node(child, code_bytes))
    else:
        extracted.extend(process_single_node(node, code_bytes))
    return extracted

def main():
    import argparse
    parser_arg = argparse.ArgumentParser()
    parser_arg.add_argument("input_file")
    parser_arg.add_argument("output_file")
    parser_arg.add_argument("--staggered", action="store_true")
    args = parser_arg.parse_args()

    with open(args.input_file, 'r', encoding='utf-8') as f:
        code = f.read()

    parser = get_cpp_parser()
    tree = parser.parse(bytes(code, 'utf8'))
    
    def find_main(n):
        if n.type == 'function_definition':
            decl = n.child_by_field_name('declarator')
            if decl and b'main' in decl.text: return n
        for c in n.children:
            res = find_main(c)
            if res: return res
        return None

    main_node = find_main(tree.root_node)
    if main_node:
        body = main_node.child_by_field_name('body')
        code_data = process_compound(body, bytes(code, 'utf8'))
        data = [('start', 'Начало')] + code_data + [('end', 'Конец')]
        
        renderer = VerticalMainRenderer(staggered=args.staggered)
        renderer.render_nodes(data, is_first=True)
        renderer.save(args.output_file)
        print(f"Saved {args.output_file}")

if __name__ == "__main__":
    main()
