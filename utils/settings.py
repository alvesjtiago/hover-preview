import sublime  # type: ignore


class Settings:

    preview_on_hover = True
    search_mode = "project"
    recursive = True
    image_folder_name = "Previewed Images"
    formats_to_convert = ["svg", "svgz", "ico", "webp"]

    @classmethod
    def update(cls, loaded_settings):

        cls.preview_on_hover = loaded_settings.get("preview_on_hover", True)
        cls.search_mode = loaded_settings.get("search_mode", "project")
        cls.recursive = loaded_settings.get("recursive", True)
        cls.image_folder_name = loaded_settings.get("image_folder_name", "Previewed Images")
        cls.formats_to_convert = loaded_settings.get("formats_to_convert", ["svg", "svgz", "ico", "webp"])
