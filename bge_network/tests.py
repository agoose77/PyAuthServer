from network import Attribute


class PlayerController:

    def fire_weapon(self):
        self.server_fire()
        self.client_fire()

    def client_fire(self):
        self.pawn.weapon_attachment.play_effects()

    def server_fire(self):
        self.weapon.fire()
        self.pawn.fire_count += 1


class Pawn:

    fire_count = Attribute(0, notify=True, complain=True)

    def on_notify(self, name):
        if name == "fire_count":
            self.weapon_attachment.play_effects()
        else:
            super().on_notify(name)


class Weapon:

    def fire(self):
        pass


class WeaponAttachment:

    def play_effects(self):
        pass