from . import command_manager, global_command


@command_manager.CommandManager.register
class BackCommand(global_command.GlobalCommand):
    command_name = "back"
    prompt_event_description = "Only when current UI state is absoultely wrong from our goal path, '\
        'use this funciton to back to previous page. Most time, you don't need to use this function."
    prompt_description_in_elements = "Back to previous page"

    perform_on_element = False

    def perform_action(self, element, extra_data):
        self.driver.back()
        return "Back to previous page"
