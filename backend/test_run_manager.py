from app.services.run_manager import RunManager

def main():
    rm = RunManager(seed=123)
    rm.start()

    for _ in range(5):
        d = rm.step()
        print("tick", d["tick"], "| events:", d["events"], "| ended:", d.get("ended"))

    print("Replay saved to:", rm.logger.path)

if __name__ == "__main__":
    main()
