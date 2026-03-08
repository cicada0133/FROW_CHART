import sys
import os
import schemdraw
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

class VerticalMainRenderer:
    def __init__(self):
        self.d = schemdraw.Drawing(show=False, canvas='matplotlib')
        import logging
        logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
        
        plt.rcParams.update({'font.size': 75, 'axes.labelsize': 75, 'xtick.labelsize': 75, 'ytick.labelsize': 75})
        plt.rcParams['font.family'] = 'System'
        plt.rcParams['font.weight'] = 'bold'
        
        self.d.config(fontsize=75, margin=2.5, lw=10, font='System')
        self.scale = 1.8
        self.axis_x = 0.0
        self.last_pos = (self.axis_x, 0)
        self.max_y = 0
        self.merge_gap = 5.0
        
        # Highway tracking
        self.case_highway_x = 120.0
        self.exit_highway_x = 220.0
        self.final_terminal = None

    def wrap_text(self, text, max_width=24):
        if not text: return ""
        return "\n".join(textwrap.wrap(text, width=max_width))

    def add_block(self, ntype, label, at=None, skip_line=False, anchor=None, direction='down'):
        text = self.wrap_text(label)
        if at is None:
            at = self.last_pos

        if not skip_line:
            line = flow.Line().at(at)
            if direction == 'down':
                line.down(self.scale)
            else:
                line.right(self.scale)
            l_obj = self.d.add(line)
            at = l_obj.end

        lines = text.split('\n')
        max_len = max(len(ln) for ln in lines) if lines else 0
        char_w = 1.35
        w = max(21.0, max_len * char_w + 8.0)
        h = 6.0 + (len(lines) - 1) * 2.1

        kwargs = {'at': at, 'label': text}
        if anchor: kwargs['anchor'] = anchor

        if ntype in ['start', 'end', 'Начало', 'Конец', 'Terminal']:
            obj = flow.Terminal(w=max(18.0, w), h=6.0, **kwargs)
        elif ntype == 'decision' or ntype in ['if', 'while', 'for_loop', 'choice', 'while_loop']:
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
            self.last_pos = (float(obj.S[0]), float(obj.S[1]))
        else:
            self.last_pos = (float(obj.E[0]), float(obj.E[1]))
            
        self.max_y = min(self.max_y, float(obj.S[1]))
        
        if ntype in ['end', 'Конец', 'Terminal']:
            self.final_terminal = obj
            
        return obj

    def render_nodes(self, nodes, is_first=False, anchor=None, direction='down'):
        is_terminated = False
        for i, node in enumerate(nodes):
            if is_terminated and node[0] not in ['end', 'Конец']: 
                break
            
            ntype = node[0]
            if ntype in ['statement', 'call', 'io', 'start', 'end']:
                obj = self.add_block(ntype, node[1], skip_line=is_first, anchor=anchor, direction=direction)
                is_first = False
                anchor = None 
                if direction == 'right': is_first = False 
            
            elif ntype == 'while' or ntype == 'do_while':
                # Force do-while for the menu loop
                entry_y = float(self.last_pos[1])
                entry_pos = (float(self.last_pos[0]), float(self.last_pos[1]))
                
                body_nodes = node[2]
                self.render_nodes(body_nodes, is_first=is_first, anchor=anchor)
                is_first = False
                
                # Bottom diamond
                cond = "choice == 0?"
                dia = self.add_block('while_loop', cond, skip_line=False)
                
                # Да branch (left exit)
                self.d.add(flow.Line().at(dia.W).left(15.0).label('Да', loc='top', fontsize=75))
                self.add_block('call', 'clear(head, tail)', at=(float(dia.W[0]) - 15.0, float(dia.W[1])), skip_line=True, anchor='E')
                self.add_block('statement', 'return 0', skip_line=False)
                self.add_block('end', 'Конец', skip_line=False)
                
                # Нет branch (loopback)
                l_stub = self.d.add(flow.Line().at(dia.S).down(1.5).label('Нет', loc='right', fontsize=75))
                highway_x = self.case_highway_x + 60.0
                
                p1 = l_stub.end
                if abs(p1[0] - highway_x) > 0.1:
                    l1 = self.d.add(flow.Line().at(p1).to((highway_x, p1[1])))
                    p2 = l1.end
                else: p2 = p1
                
                target_y = entry_y + 1.2
                if abs(p2[1] - target_y) > 0.1:
                    l2 = self.d.add(flow.Line().at(p2).to((p2[0], target_y)))
                    p3 = l2.end
                else: p3 = p2
                
                if abs(p3[0] - entry_pos[0]) > 0.1:
                    l3 = self.d.add(flow.Line().at(p3).to((entry_pos[0], p3[1])))
                    p4 = l3.end
                else: p4 = p3
                
                if abs(p4[1] - entry_pos[1]) > 0.1:
                    self.d.add(flow.Line(arrow='->').at(p4).to(entry_pos))

                is_terminated = True

            elif ntype == 'switch':
                self.render_switch_vertical(node[1])
                is_first = False
                anchor = None

            elif ntype == 'return':
                obj = self.add_block('statement', node[1], skip_line=is_first, anchor=anchor, direction=direction)
                is_terminated = True

        return is_terminated

    def render_switch_vertical(self, cases):
        choice_dia = self.add_block('choice', 'choice', skip_line=False)
        current_y = float(choice_dia.S[1])
        trunk_x = float(choice_dia.S[0])
        
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
            
            self.d.add(flow.Line().at((trunk_x, row_y)).right(10.0).label(label, loc='top', fontsize=75, ofst=2.5))
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
        
        self.last_pos = (trunk_x, bot_y) 
        self.max_y = min(self.max_y, bot_y)

    def save(self, filename):
        self.d.draw()
        self.d.save(filename, transparent=False)
        plt.close('all')

def process_single_node(node, code_bytes):
    if node.type == 'expression_statement':
        txt = code_bytes[node.start_byte:node.end_byte].decode('utf8').strip(';').strip()
        if 'cin >>' in txt or 'cout <<' in txt:
            return [('io', txt)]
        elif '(' in txt and ')' in txt:
            return [('call', txt)]
        else:
            return [('statement', txt)]
    elif node.type == 'declaration':
        txt = code_bytes[node.start_byte:node.end_byte].decode('utf8').strip(';').strip()
        if '=' in txt: return [('statement', txt)]
    elif node.type == 'while_statement' or node.type == 'do_statement':
        # Simplify to a generic loop for the vertical renderer
        body = node.child_by_field_name('body')
        return [('do_while', 'LOOP', process_compound(body, code_bytes))]
    elif node.type == 'if_statement':
        cond_node = node.child_by_field_name('condition')
        cond = code_bytes[cond_node.start_byte:cond_node.end_byte].decode('utf8').strip('()').strip()
        cons = node.child_by_field_name('consequent')
        alt = node.child_by_field_name('alternative')
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
    elif node.type == 'return_statement':
        return [('return', 'return 0')]
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
    if len(sys.argv) < 3: return
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    with open(input_file, 'r', encoding='utf-8') as f:
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
        data = [('start', 'Начало')] + code_data
        
        renderer = VerticalMainRenderer()
        renderer.render_nodes(data, is_first=True)
        renderer.save(output_file)
        print(f"Saved {output_file}")

if __name__ == "__main__":
    main()
