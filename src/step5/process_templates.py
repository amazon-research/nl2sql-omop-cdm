import re
import config

SCHEMA_P = re.compile('<SCHEMA>')

# template-based placeholders
PLACE_HOLDER_P = re.compile('<\w*-TEMPLATE><ARG-\w*><\d+>')
PLACE_HOLDER_META_P = re.compile('(<\w*-TEMPLATE>)<ARG-(\w*)><(\d+)>')

# non template-based placeholders
ARG_PLACE_HOLDER_P = re.compile('<ARG-\w*><\d+>')
ARG_PLACE_HOLDER_META_P = re.compile('<ARG-(\w*)><(\d+)>')

# non template-based placeholders
TEMPLATE_PLACE_HOLDER_P = re.compile('<\w*-TEMPLATE>')


def render_template_query(config, current_query, args_dict):

    # Render <SCHEMA> placeholder
    current_query = re.sub(SCHEMA_P, config.SCHEMA, current_query)

    # Render "<\w*-TEMPLATE><ARG-\w*><\d+>" placeholders. E.g. descendent templates. 
    item = re.search(PLACE_HOLDER_P, current_query)
    placeholder2templates = config.placeholder2template['with_arg']
    while item:

        start, end = item.start(0), item.end(0)
        place_holder = current_query[start:end]

        # extract metadta from placeholder
        template_type, domain, idx = re.findall(PLACE_HOLDER_META_P, place_holder)[0]

        # retrieve concept name
        idx = int(idx)
        concept_name = args_dict[domain][idx]

        # retrieve rendered sub-query
        sub_query = placeholder2templates[template_type](config.SCHEMA, concept_name)

        # replace in current query
        current_query = current_query[:start] + sub_query +  current_query[end:]

        # search for next placeholder
        item = re.search(PLACE_HOLDER_P, current_query)
        
        
    # Render "<ARG-\w*><\d+>" placeholders. E.g. days.
    item = re.search(ARG_PLACE_HOLDER_P, current_query)
    while item:

        start, end = item.start(0), item.end(0)
        place_holder = current_query[start:end]

        # extract metadta from placeholder
        domain, idx = re.findall(ARG_PLACE_HOLDER_META_P, place_holder)[0]

        # retrieve argument value
        idx = int(idx)
        arg_value = args_dict[domain][idx]

        # replace argument value in current-query
        current_query = current_query[:start] + arg_value +  current_query[end:]

        # search for next placeholder
        item = re.search(ARG_PLACE_HOLDER_P, current_query)
        
        
    # Render "<\w*-TEMPLATE>" placeholders. E.g. Location names 
    item = re.search(TEMPLATE_PLACE_HOLDER_P, current_query)
    placeholder2templates = config.placeholder2template['with_no_arg']
    while item:

        start, end = item.start(0), item.end(0)
        place_holder = current_query[start:end]

        # extract metadata from placeholder
        sub_query = placeholder2templates[place_holder]
        
        # replace argument value in current-query
        current_query = current_query[:start] + sub_query +  current_query[end:]

        # search for next placeholder
        item = re.search(TEMPLATE_PLACE_HOLDER_P, current_query)
    
    return current_query