from . import base


class GlobalCommand(base.BaseCommand):
    perform_on_element = False
    perform_on_global = True
    prompt_description_in_elements: str

    @classmethod
    def get_prompt_element_description(cls, element):
        return False
