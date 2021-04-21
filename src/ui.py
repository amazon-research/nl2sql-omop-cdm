import ipywidgets as widgets
from ipywidgets import Layout, Text, Textarea, Dropdown, Combobox, Button, Output, HBox, VBox, Tab
import re
from spacy import displacy
import config
from IPython.core.display import display, HTML
from copy import deepcopy
import time
from pprint import pprint

MAIN_BOX_LAYOUT = Layout(flex='1 1 auto', height='800px', min_height='50px', width='auto')
MAIN_INTERFACE_LAYOUT = Layout(height='45%', width='90%')# flex='0 1 auto',
MAIN_DISPLAY_LAYOUT = Layout(flex='0 1 auto', height='55%', width='90%', border='1px solid black')

INPUT_BOX_LAYOUT = Layout(flex='1 1 auto', height='100%', min_height='50px', width='auto')
INPUT_TEXT_LAYOUT = Layout(height='90%', width='90%')# flex='0 1 auto',
# INPUT_DISPLAY_LAYOUT = Layout(flex='0 1 auto', height='70%', width='90%', border='1px solid black')

DETECT_BOX_LAYOUT = Layout(flex='1 1 auto', height='40%', min_height='50px', width='auto')
INFO_BOX_LAYOUT =  Layout(flex='1 1 auto', height='100%', min_height='50px', width='auto')
# INPUT_TEXT_LAYOUT = Layout(flex='0 1 auto', height='95%', width='90%')

RENDERER = displacy.EntityRenderer(options={})

RENDERER.colors = {
    'DRUG': '#7aecec',
    'CONDITION': '#bfeeb7',
    'AGE': '#feca74',
    'STATE': '#ff9561',
    'ETHNICITY': '#aa9cfc',
    'RACE': '#c887fb',
    'TIMEDAYS': '#bfe1d9',
    'TIMEYEARS': '#bfe1d9',
    'GENDER': '#e4e7d2',
#     'FACILITY': '#9cc9cc',
#     'EVENT': '#ffeb80',
#     'LAW': '#ff8197',
#     'LANGUAGE': '#ff8197',
#     'WORK_OF_ART': '#f0d0ff'
}

def reformat_raw_entities(entities):
    out = [{
        'start': name_dict['BeginOffset'],
        'end': name_dict['EndOffset'],
        'label': category
           } 
           for category, name_dicts in entities.items() 
           for name_dict in name_dicts
          ]
    out = sorted(out, key=lambda x: x['start'])
    return out

def raw_converter(text, entities):
    ents = reformat_raw_entities(entities)
    out = {
        'text': text,
        'ents': ents,
        'title': None,
        'settings': {'lang': 'en', 'direction': 'ltr'}
    }
    return out


def get_reformatted_proc_entities(text, entities):
    out = []
    for category, name_dicts in entities.items():
        for name_dict in name_dicts:
            repl_text = name_dict['Query-arg']
            p = re.compile(f"(?i)\\b{repl_text}\\b")
            match = list(re.finditer(p, text))[0]
            out.append({
                'start': match.start(),
                'end': match.end(),
                'label': category
            })
    out = sorted(out, key=lambda x: x['start'])
    return out


def get_reformatted_nlq(text, entities):
    out_text = deepcopy(text)
    for cat_entities in entities.values():
        for entity in cat_entities:
            orig_text = entity['Text']
            p = re.compile(f"(?i)\\b{orig_text}\\b")
            repl_text = entity['Query-arg']
            out_text = re.sub(p, repl_text, out_text)
    return out_text


def proc_converter(text, entities):
    text2 = get_reformatted_nlq(text, entities)
    ents = get_reformatted_proc_entities(text2, entities)
    out = {
        'text': text2,
        'ents': ents,
        'title': None,
        'settings': {'lang': 'en', 'direction': 'ltr'}
    }
    return out



class UI(object):
    
    def __init__(self, tool):
        
        self.tool = tool
        
        self._initialize_inputs()
        self._initialize_add_detection()
        self._initialize_mapped_values()
        
        
        
        children = [self.input_disp_box, self.add_detection_box, self.disambiguate_box]#, self.add_detection_box]
        self.tab = Tab(layout=MAIN_INTERFACE_LAYOUT)
        self.tab.children = children
        self.tab.set_title(0, 'Main')
        self.tab.set_title(1, 'Correct detection')
        self.tab.set_title(2, 'Correct code map')
        
        self.main_display = Output(layout=MAIN_DISPLAY_LAYOUT)
        
        self.main_ui = VBox([self.tab, self.main_display], layout = MAIN_BOX_LAYOUT)
        
        
        
    def visualize_entities(self, entities, converter):
        parsed = [converter(self.nlq, entities)]
        html = RENDERER.render(parsed, page=False, minify=False).strip()
        return HTML('<span class="tex2jax_ignore">{}</span>'.format(html))


    def _display_main(self):
        self.main_display.clear_output()
        
        self.main_display.append_stdout('\n The following key entities have been detected:')
        html_detected_entities = self.visualize_entities(self.entities, raw_converter)
        self.main_display.append_display_data(html_detected_entities)
        
        self.main_display.append_stdout('\n Drugs and Conditions will be respectively replaced by the following RxNorm & ICD10 codes:')
        html_replaced_entities = self.visualize_entities(self.proc_entities, proc_converter)
        self.main_display.append_display_data(html_replaced_entities)
    
    
    def _helper_detect_button(self, b):
        self.nlq = self.input_box.value
        self.entities = self.tool.detect_entities(self.nlq)
        self.proc_entities = self.tool.process_entities(self.entities)
        
        self._display_main()
        
        self.mapped_drug_category.options = [d['Text'] for d in self.entities['DRUG']]
        self.mapped_condition_category.options = [d['Text'] for d in self.entities['CONDITION']]
        
        
    def _helper_execute_button(self, b):
        nlq_w_placeholders = self.tool.replace_name_for_placeholder(self.nlq, self.proc_entities)
        sql_query = self.tool.ml_call(nlq_w_placeholders)
        rendered_sql_query = self.tool.render_template_query(sql_query, self.proc_entities)
        df = self.tool.execute_sql_query(rendered_sql_query)
        
        self.main_display.clear_output()
        with self.main_display:
            display(df)
            
    
    def _initialize_inputs(self):
        
        self.input_box = Textarea(
            placeholder='e.g. Number of patients taking Aspirin',
            description='Query:',
            layout=INPUT_TEXT_LAYOUT,
            disabled=False
        )
        self.detect_button = Button(description="Detect")
        self.detect_button.on_click(self._helper_detect_button)
        self.execute_button = Button(description="Execute")
        self.execute_button.on_click(self._helper_execute_button)
        
        self.main_buttons = HBox([self.detect_button, self.execute_button])
        self.input_disp_box = VBox([self.input_box, self.main_buttons], layout=INPUT_BOX_LAYOUT)
        
    
    def _record_name(self, b):
        p = re.compile(f"(?i)\\b{self.name.value}\\b")
        # current entities set
        current_names = set([d['Text'] for d in self.entities[self.category.value]])
        if self.name.value not in current_names:
            for match in re.finditer(p, self.nlq):
                detected_entity = {
                        'BeginOffset': match.start(),
                        'EndOffset': match.end(),
                        'Text': self.name.value
                }
                self.entities[self.category.value].append(
                    deepcopy(detected_entity)
                )
                
                # process & add to proc entities
                placeholder_idx_strat = {
                    self.category.value: len(self.proc_entities[self.category.value])
                }
                proc_detected_entity = self.tool.process_entities(
                    {self.category.value: [deepcopy(detected_entity)]}, 
                    start_indices=placeholder_idx_strat
                )
                self.proc_entities[self.category.value].append(
                    proc_detected_entity[self.category.value][0]
                )
                
        self._display_main()
        self.mapped_drug_category.options = [d['Text'] for d in self.entities['DRUG']]
        self.mapped_condition_category.options = [d['Text'] for d in self.entities['CONDITION']]
        
    
    
    def _initialize_add_detection(self):
        
        
        self.name = Text(
            placeholder='Aspirin 30Mg',
            description='Write name',
#             layout=TEXT_LAYOUT,
            disabled=False
        )
        self.category = Dropdown(
            # value='John',
            placeholder='Choose entity',
            options=['DRUG', 'CONDITION', 'AGE', 'STATE', 'ETHNICITY', 'RACE', 'TIMEDAYS', 'TIMEYEARS', 'GENDER'],
            description='Category:',
            ensure_option=True,
            disabled=False
        )
        self.detect_button = Button(description="Highlight")
        self.detect_button.on_click(self._record_name)
        
        self.add_detection_box = HBox([self.name, self.category, self.detect_button], layout=DETECT_BOX_LAYOUT)
           
    
    def _visualize_drug_info(self,):
    
        # get dictionary of selected text
        entity_dict = [d for d in self.proc_entities['DRUG'] if d['Text'] == self.mapped_drug_category.value][0]
        
        # output text
        lines = ["\t\t\t     TEXT: {}".format(entity_dict['Text'])]
        lines.append("\t\t\tDISAMBIGUATED TO: {}\n".format(entity_dict['Query-arg']))
        lines.append("INFERRED OPTIONS")
        lines.append("    Score\tRxNorm Code   \tName\n")
        for i, d in enumerate(entity_dict['Options'], 1):
            lines.append("{}. ({:.3f})\t {:7d} \t{}".format(i, d['Score'], int(d['Code']), d['Description']))
        text = '\n'.join(lines)
        
        # display
        self.mapped_out.clear_output()
        self.mapped_out.append_stdout(text)
        
        
    def _visualize_condition_info(self,):
        # get dictionary of selected text
        entity_dict = [d for d in self.proc_entities['CONDITION'] if d['Text'] == self.mapped_condition_category.value][0]
        
        # output text
        lines = ["\t\t\t     TEXT: {}".format(entity_dict['Text'])]
        lines.append("\t\t\tDISAMBIGUATED TO: {}\n".format(entity_dict['Query-arg']))
        lines.append("INFERRED OPTIONS")
        lines.append("    Score\tICD10 Code   \tName\n")
        for i, d in enumerate(entity_dict['Options'], 1):
            lines.append("{}. ({:.3f})\t {:7s} \t{}".format(i, d['Score'], d['Code'], d['Description']))
        text = '\n'.join(lines)
        
        # display
        self.mapped_out.clear_output()
        self.mapped_out.append_stdout(text)
        
    
    def _drug_info(self, b):
        self._visualize_drug_info()
        
    
    def _condition_info(self, b):
        self._visualize_condition_info()
        
    
    def _drug_update(self, b):
        for d in self.proc_entities['DRUG']:
            if d['Text'] == self.mapped_drug_category.value:
                d['Query-arg'] = self.mapped_update_drug_text.value
                break
        
        self._visualize_drug_info()
        self.main_display()
        
        
    def _condition_update(self, b):
        for d in self.proc_entities['CONDITION']:
            if d['Text'] == self.mapped_condition_category.value:
                d['Query-arg'] = self.mapped_update_condition_text.value
                break
        
        self._visualize_condition_info()
        self.main_display()
    
    
    def _initialize_mapped_values(self,):
        
#         DRUG
        drugs = [d['Text'] for d in self.entities['DRUG']] if hasattr(self, 'entities') else []
        self.mapped_drug_category = Dropdown(
            placeholder='e.g. Aspirin',
            options=drugs,
            description='Drug',
            ensure_option=True,
            disabled=False
        )
        self.mapped_drug_button = Button(description="Show drug info")
        self.mapped_drug_button.on_click(self._drug_info)
        self.mapped_update_drug_text = Text(
            placeholder='RxNorm code',
            description='Map to',
#             layout=TEXT_LAYOUT,
            disabled=False
        )
        self.mapped_update_drug_button = Button(description="Update drug")
        self.mapped_update_drug_button.on_click(self._drug_update)
        
#         CONDITION
        conditions = [d['Text'] for d in self.entities['CONDITION']] if hasattr(self, 'entities') else []
        self.mapped_condition_category = Dropdown(
            placeholder='e.g. Insomnia',
            options=conditions,
            description='Condition',
            ensure_option=True,
            disabled=False
        )
        self.mapped_condition_button = Button(description="Show condition info")
        self.mapped_condition_button.on_click(self._condition_info)
        self.mapped_update_condition_text = Text(
            placeholder='ICD10 code',
            description='Map to',
#             layout=TEXT_LAYOUT,
            disabled=False
        )
        self.mapped_update_condition_button = Button(description="Update condition")
        self.mapped_update_condition_button.on_click(self._condition_update)
        
        
        self.mapped_out = Output(layout={'border': '1px solid black'})
        
        self._mapped_drug_box = HBox([self.mapped_drug_category, self.mapped_drug_button, self.mapped_update_drug_text, self.mapped_update_drug_button])
        self._mapped_condition_box = HBox([self.mapped_condition_category, self.mapped_condition_button, self.mapped_update_condition_text, self.mapped_update_condition_button])
        
        self.disambiguate_box = VBox([self._mapped_drug_box, self._mapped_condition_box, self.mapped_out], layout=INFO_BOX_LAYOUT)
        
        
    def main(self):
        display(self.main_ui)
        time.sleep(1)
        
        self.main_display.append_stdout('.')
        self.main_display.clear_output()
        self.main_display.append_stdout('.')
        time.sleep(1)
        self.main_display.clear_output()
        
        self.mapped_out.append_stdout('.')
        self.mapped_out.clear_output()
        self.mapped_out.append_stdout('.')
        time.sleep(1)
        self.mapped_out.clear_output()
        
        
