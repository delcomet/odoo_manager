# -*- coding: utf-8 -*-

{% for model in models %}
from . import {{ model.replace('.', '_') }}
{%- endfor %}

