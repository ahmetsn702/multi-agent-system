import flet as ft

def main(page: ft.Page) -> None:
    page.title = "Veri Giris Uygulamasi"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER

    input_field = ft.TextField(label="Bir metin girin", width=300)
    result_text = ft.Text(value="", size=20)

    def button_clicked(e: ft.ControlEvent) -> None:
        if input_field.value:
            result_text.value = f"Girdiginiz deger: {input_field.value}"
        else:
            result_text.value = "Lutfen bir deger girin!"
        page.update()

    page.add(
        input_field,
        ft.ElevatedButton("Gonder", on_click=button_clicked),
        result_text
    )

ft.app(target=main)