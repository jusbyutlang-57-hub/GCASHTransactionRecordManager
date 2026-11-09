import customtkinter as ctk
from ui import GCashTransactionApp
import database


def main():
    database.initialize_database()
    root = ctk.CTk()
    GCashTransactionApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()