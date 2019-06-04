
import os
import glob
import shutil
import re
import pkg_resources
import json
import datetime as dt



from jinja2 import Environment, PackageLoader
CLASS_ENV = Environment(
    loader=PackageLoader('odoo_manager', 'templates'),
)

MODULE_ENV = Environment(
    loader=PackageLoader('odoo_manager', 'module_template'),
)
    

CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
TEMPLATE = os.path.join(CURRENT_DIR, 'module_template')
CACHE_FILE = pkg_resources.resource_filename('odoo_manager', 'cache.json')




class ModuleTemplate:

    def __str__(self):
        return CLASS_ENV.get_template('ModuleTemplate').render(
            name=self.name,
            models=self.models,
            wizards=self.wizards,
            views=self.views,
            depends=self.depends,
        )

    def __repr__(self):
        return f'{self.name}: {self.module_dir}'
    
    def __init__(self, config, name):
        self.config = config
        self.name = name
        self.module_dir = os.path.join(self.config['addons_path'], self.name)
        if os.path.exists(self.module_dir):
            raise FileExistsError("Module exists: %s" % self.module_dir)
        self.wizards = set()
        self.models = set()
        self.views = set()
        self.depends = set()

        self.available_models = set()
        self.available_wizards = set()
        self.available_modules = set()

    def add(self, data_type='models', name='account.invoice'):
        getattr(self, data_type).add(name)


    def update_rendering_globals(self):
        MODULE_ENV.globals.update({
            'ModelName': lambda model: ''.join([s.capitalize() for s in model.split('.')]),
            'Title': lambda name: ' '.join([s.capitalize() for s in name.replace('.', '_').split('_')]),
            'module_name': self.name,
            'depends': self.depends,
            'first_dependency': next(iter(self.depends)) if self.depends else 'module',
            'sub_modules': [n for n in ['models', 'wizards'] if getattr(self, n)],
            'views': self.views,
            'author': self.config['author'],
        })

    def write(self):
        shutil.rmtree(self.module_dir, ignore_errors=True)

        self.update_rendering_globals()
        EXISTING_MODELS = self.available_models | self.available_wizards

        def normal_templates(template):
            specials = [
                'views',
                'models',
                'wizards',
            ]
            for special in specials:
                if special in template:
                    return False
            return True


        def render_model_templates(models, folder):
            path_content = {}
            for model in models:
                if model in EXISTING_MODELS:
                    template = MODULE_ENV.get_template('%s/inherit_model.py' % folder)
                else:
                    template = MODULE_ENV.get_template('%s/new_model.py' % folder)

                file_name = model.replace('.', '_') + '.py'
                model_path = '%s/%s' % (folder, file_name)
                path_content[model_path] = template.render(model=model)
            init = '%s/__init__.py' % folder
            path_content[init] = MODULE_ENV.get_template(init).render(models=models)
            
            return path_content

        path_content = {}

        if self.models:
            path_content.update(render_model_templates(self.models, 'models'))
        if self.wizards:
            path_content.update(render_model_templates(self.wizards, 'wizards'))
            
        for model in self.views:
            if model in EXISTING_MODELS:
                template = MODULE_ENV.get_template('views/inherited_view.xml')
            else:
                template = MODULE_ENV.get_template('views/new_view.xml')
            file_name = 'views/' + model.replace('.', '_') + '_view.xml'
            path_content[file_name] = template.render(model=model)
            

        remaining_files = set()
        for template_name in filter(normal_templates, MODULE_ENV.list_templates()):
            try:
                template = MODULE_ENV.get_template(template_name)
            except UnicodeDecodeError:
                remaining_files.add(template_name)
                continue
            path_content[template_name] = template.render()


        for file_path, data in path_content.items():
            new_path = os.path.join(self.module_dir, file_path)
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            with open(new_path, 'w') as f:
                f.write(data)

        for remaining_file in remaining_files:
            src_path = os.path.join(TEMPLATE, remaining_file)
            dest_path = os.path.join(self.module_dir, remaining_file)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copyfile(src_path, dest_path)

        return f"Template created at {self.module_dir}"

    def load_odoo_data(self, *paths):
        print("Loading available odoo modules..")
        modified = dt.datetime.utcfromtimestamp(os.path.getmtime(CACHE_FILE))
        time_passed = dt.datetime.utcnow() - modified
        if time_passed < dt.timedelta(hours=1):
            with open(CACHE_FILE) as f:
                for key, value in json.load(f).items():
                    self.__dict__[key] = set(value)
            return

        for path in paths:
            glob_path = os.path.normpath(path + f'/**/*.py')
            python_files = glob.glob(glob_path, recursive=True)
            for python_file in python_files:
                if python_file.endswith('__manifest__.py'):
                    self.available_modules.add(os.path.basename(os.path.dirname(python_file)))
                    continue
                with open(python_file) as f:
                    results = re.findall(r'''models\.([\w]+)[\w\W]*?[\W]_name = ['"](.*?)['"]''', f.read())
                for match in results:
                    model_type, model_name = match
                    if model_type == 'Model':
                        self.available_models.add(model_name)
                    elif model_type == 'TransientModel':
                        self.available_wizards.add(model_name)

        with open(CACHE_FILE, 'w') as f:
            json.dump({
                'available_models': list(self.available_models),
                'available_wizards': list(self.available_wizards),
                'available_modules': list(self.available_modules),
            }, f, indent=4)
